import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import config
from db import session_commit, session_execute
from enums.bank_payment_status import BankPaymentStatus
from enums.buy_status import BuyStatus
from models.bank_payment import BankPaymentDTO
from models.buy import Buy
from models.item import Item
from repositories.bank_payment import BankPaymentRepository
from services.notification import NotificationService


class SePayService:
    PAYMENT_CODE_RE = re.compile(rf"{re.escape(config.SEPAY_PAYMENT_PREFIX)}\s*(\d+)", re.IGNORECASE)
    PAYMENT_TYPE_FULL = "FULL"
    PAYMENT_TYPE_DEPOSIT = "DEPOSIT"
    DEPOSIT_PERCENT = 0.30
    DEPOSIT_SURCHARGE_PERCENT = 0.05
    ROUNDING_UNIT = 1000

    @staticmethod
    def create_payment_code(buy_id: int) -> str:
        return f"{config.SEPAY_PAYMENT_PREFIX}{buy_id}"

    @staticmethod
    def create_vietqr_url(amount: float, payment_code: str) -> str:
        account_name = quote_plus(config.SEPAY_ACCOUNT_NAME or "SHOP")
        add_info = quote_plus(payment_code)
        return (
            f"https://img.vietqr.io/image/{config.SEPAY_BANK_CODE}-{config.SEPAY_ACCOUNT_NUMBER}-"
            f"{config.SEPAY_QR_TEMPLATE}.png?amount={int(amount)}&addInfo={add_info}&accountName={account_name}"
        )

    @staticmethod
    def extract_payment_code(content: str | None) -> str | None:
        if not content:
            return None
        match = SePayService.PAYMENT_CODE_RE.search(content)
        if match is None:
            return None
        return f"{config.SEPAY_PAYMENT_PREFIX}{match.group(1)}"

    @staticmethod
    def _parse_amount(amount) -> float:
        if amount is None:
            return 0
        if isinstance(amount, int | float):
            return float(amount)
        amount_text = str(amount).strip().replace("+", "")
        if "," in amount_text and "." in amount_text:
            amount_text = amount_text.replace(".", "").replace(",", ".")
        else:
            amount_text = amount_text.replace(".", "").replace(",", "")
        return float(amount_text or 0)

    @staticmethod
    def parse_payload(payload: dict) -> tuple[str, float, str]:
        transaction_id = str(payload.get("id") or payload.get("transaction_id") or payload.get("referenceCode") or "")
        amount = (payload.get("transferAmount") or payload.get("transfer_amount") or payload.get("amount")
                  or payload.get("money") or payload.get("amountIn") or 0)
        content_parts = [
            payload.get("content"),
            payload.get("description"),
            payload.get("transferContent"),
            payload.get("transfer_content"),
            payload.get("code"),
            payload.get("referenceCode"),
        ]
        content = " ".join(str(part) for part in content_parts if part)
        return transaction_id, SePayService._parse_amount(amount), content

    @staticmethod
    def _format_vnd(amount: float | int | None) -> str:
        return f"₫{float(amount or 0):,.0f}"

    @staticmethod
    def _format_buyer(buy: Buy) -> str:
        if not buy.buyer:
            return "- Chưa có thông tin khách"
        username = f"@{escape(buy.buyer.telegram_username)}" if buy.buyer.telegram_username else "Chưa có username"
        return f"- Telegram: {username}\n- Telegram ID: <code>{buy.buyer.telegram_id}</code>"

    @staticmethod
    def _format_shipping_address(address: str | None) -> tuple[str, str]:
        if not address:
            return "<i>Chưa có địa chỉ giao hàng.</i>", "⚠️ Đơn này chưa có địa chỉ giao hàng. Cần nhắn khách bổ sung."
        safe_address = escape(address.strip())
        warning = ""
        if not re.search(r"(?:\+?84|0)(?:\s|\.|-)?(?:3|5|7|8|9)(?:\d(?:\s|\.|-)?){8}\b", address):
            warning = "⚠️ Chưa thấy số điện thoại trong địa chỉ. Cần kiểm tra/nhắn khách bổ sung."
        return safe_address, warning

    @staticmethod
    def _format_items(items: list[Item]) -> str:
        if not items:
            return "<i>Chưa có sản phẩm trong đơn.</i>"
        lines = []
        for index, item in enumerate(items, start=1):
            description = escape(item.description or f"Sản phẩm #{item.id}")
            lines.append(f"{index}. {description} — {SePayService._format_vnd(item.price)}")
        return "\n".join(lines)

    @staticmethod
    def _build_paid_admin_message(
        buy: Buy,
        payment_code: str,
        paid_amount: float,
        transaction_id: str,
        items: list[Item],
    ) -> str:
        shipping_address, shipping_warning = SePayService._format_shipping_address(buy.shipping_address)
        warning_block = f"\n\n{shipping_warning}" if shipping_warning else ""
        transaction_text = escape(transaction_id) if transaction_id else "Không có"
        return (
            f"✅ Đơn hàng #{buy.id} đã thanh toán qua SePay\n"
            f"Mã CK: <code>{payment_code}</code>\n"
            f"Số tiền: {SePayService._format_vnd(paid_amount)}\n"
            f"Mã GD: <code>{transaction_text}</code>\n\n"
            f"👤 Khách hàng:\n{SePayService._format_buyer(buy)}\n\n"
            f"📦 Sản phẩm:\n{SePayService._format_items(items)}\n\n"
            f"🚚 Địa chỉ giao hàng:\n{shipping_address}"
            f"{warning_block}\n\n"
            f"👉 Việc cần làm: chuẩn bị hàng và giao cho khách."
        )

    @staticmethod
    def calculate_deposit_amounts(original_total: float) -> tuple[float, float, float]:
        surcharge_total = SePayService._round_up(original_total * (1 + SePayService.DEPOSIT_SURCHARGE_PERCENT))
        deposit_amount = SePayService._round_up(surcharge_total * SePayService.DEPOSIT_PERCENT)
        remaining_amount = surcharge_total - deposit_amount
        return surcharge_total, deposit_amount, remaining_amount

    @staticmethod
    def _round_up(amount: float, unit: int | None = None) -> float:
        unit = unit or SePayService.ROUNDING_UNIT
        return float(((int(amount) + unit - 1) // unit) * unit)

    @staticmethod
    async def create_pending_payment(
        buy_id: int,
        amount: float,
        session: AsyncSession,
        payment_type: str = PAYMENT_TYPE_FULL,
        order_total_amount: float | None = None,
        remaining_amount: float | None = None,
    ) -> BankPaymentDTO:
        payment_code = SePayService.create_payment_code(buy_id)
        return await BankPaymentRepository.create(BankPaymentDTO(
            buy_id=buy_id,
            payment_code=payment_code,
            expected_amount=amount,
            payment_type=payment_type,
            order_total_amount=order_total_amount or amount,
            remaining_amount=remaining_amount,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=config.SEPAY_PAYMENT_TTL_MINUTES)
        ), session)

    @staticmethod
    async def handle_webhook(payload: dict, session: AsyncSession) -> dict:
        transaction_id, paid_amount, content = SePayService.parse_payload(payload)
        if transaction_id:
            existing = await BankPaymentRepository.get_by_transaction_id(transaction_id, session)
            if existing is not None:
                return {"status": "ok", "message": "duplicate"}

        payment_code = SePayService.extract_payment_code(content)
        if payment_code is None:
            await NotificationService.send_to_admins(
                f"⚠️ Giao dịch SePay không khớp mã đơn.\nSố tiền: ₫{paid_amount:,.0f}\nNội dung: <code>{content}</code>",
                None
            )
            return {"status": "unmatched"}

        payment = await BankPaymentRepository.get_model_by_payment_code(payment_code, session)
        if payment is None:
            await NotificationService.send_to_admins(
                f"⚠️ Không tìm thấy đơn cho mã CK <code>{payment_code}</code>.\nSố tiền: ₫{paid_amount:,.0f}",
                None
            )
            return {"status": "not_found"}

        if payment.status == BankPaymentStatus.PAID:
            return {"status": "ok", "message": "already_paid"}

        payment.paid_amount = paid_amount
        payment.sepay_transaction_id = transaction_id or None
        payment.raw_payload = json.dumps(payload, ensure_ascii=False)
        payment.paid_at = datetime.now(timezone.utc)

        buy = (await session_execute(
            select(Buy).options(selectinload(Buy.buy_items), selectinload(Buy.buyer)).where(Buy.id == payment.buy_id),
            session
        )).scalar_one()
        if paid_amount < payment.expected_amount:
            payment.status = BankPaymentStatus.UNDERPAID
            buy.status = BuyStatus.PAYMENT_FAILED
            await session_commit(session)
            await NotificationService.send_to_admins(
                f"⚠️ Đơn #{buy.id} chuyển thiếu tiền.\nCần: {SePayService._format_vnd(payment.expected_amount)}\nĐã nhận: {SePayService._format_vnd(paid_amount)}\nMã CK: <code>{payment_code}</code>",
                None
            )
            return {"status": "underpaid"}

        purchased_items: list[Item] = []
        for buy_item in buy.buy_items:
            items = (await session_execute(select(Item).where(Item.id.in_(buy_item.item_ids)), session)).scalars().all()
            purchased_items.extend(items)
            for item in items:
                if item.is_sold:
                    await NotificationService.send_to_admins(
                        f"⚠️ Đơn #{buy.id} đã thanh toán nhưng có sản phẩm vừa hết/đã bán. Cần xử lý thủ công.",
                        None
                    )
                    return {"status": "stock_conflict"}
                item.is_sold = True

        payment.status = BankPaymentStatus.PAID
        is_deposit = payment.payment_type == SePayService.PAYMENT_TYPE_DEPOSIT
        buy.status = BuyStatus.DEPOSIT_PAID if is_deposit else BuyStatus.PAID
        await session_commit(session)
        if is_deposit:
            shipping_address, shipping_warning = SePayService._format_shipping_address(buy.shipping_address)
            warning_block = f"\n\n{shipping_warning}" if shipping_warning else ""
            await NotificationService.send_to_admins(
                f"🟡 Đơn hàng #{buy.id} đã đặt cọc 30% qua SePay\n"
                f"Mã CK: <code>{payment_code}</code>\n"
                f"Mã GD: <code>{escape(transaction_id) if transaction_id else 'Không có'}</code>\n\n"
                f"💎 Giá thanh toán full: {SePayService._format_vnd(buy.total_price / (1 + SePayService.DEPOSIT_SURCHARGE_PERCENT))}\n"
                f"🤝 Giá đặt cọc (+5%): {SePayService._format_vnd(payment.order_total_amount or buy.total_price)}\n"
                f"Đã nhận cọc: {SePayService._format_vnd(paid_amount)}\n"
                f"Còn lại: {SePayService._format_vnd(payment.remaining_amount)}\n\n"
                f"👤 Khách hàng:\n{SePayService._format_buyer(buy)}\n\n"
                f"📦 Sản phẩm:\n{SePayService._format_items(purchased_items)}\n\n"
                f"🚚 Địa chỉ giao hàng:\n{shipping_address}"
                f"{warning_block}\n\n"
                f"👉 Việc cần làm: giữ hàng và liên hệ khách phần còn lại.",
                None
            )
        else:
            await NotificationService.send_to_admins(
                SePayService._build_paid_admin_message(buy, payment_code, paid_amount, transaction_id, purchased_items),
                None
            )
        if buy.buyer and buy.buyer.telegram_id:
            if is_deposit:
                await NotificationService.send_to_user(
                    f"✅ Shop đã nhận cọc đơn #{buy.id}.\n"
                    f"Đã nhận: {SePayService._format_vnd(paid_amount)}\n"
                    f"Còn lại: {SePayService._format_vnd(payment.remaining_amount)}\n"
                    f"Đơn của anh/chị đang được giữ hàng. Shop sẽ liên hệ phần còn lại nha 🚚",
                    buy.buyer.telegram_id
                )
            else:
                await NotificationService.send_to_user(
                    f"✅ Shop đã nhận thanh toán đơn #{buy.id}.\nSố tiền: {SePayService._format_vnd(paid_amount)}\nĐơn của anh/chị đang được chuẩn bị giao nha 🚚",
                    buy.buyer.telegram_id
                )
        return {"status": "paid", "buy_id": buy.id}
