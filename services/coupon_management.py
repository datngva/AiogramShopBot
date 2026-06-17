import secrets
import string

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

import config
from callbacks import CouponManagementCallback, AdminMenuCallback
from db import session_commit
from enums.bot_entity import BotEntity
from enums.coupon_number_of_uses import CouponNumberOfUses
from enums.coupon_payment_scope import CouponPaymentScope
from enums.coupon_type import CouponType
from enums.language import Language
from handlers.admin.constants import CouponsManagementStates
from handlers.common.common import add_pagination_buttons
from models.coupon import CouponDTO
from repositories.coupon import CouponRepository
from services.notification import NotificationService
from utils.utils import get_text


class CouponManagementService:
    @staticmethod
    def _format_usage_limit(value: int, language: Language) -> str:
        if value == 0:
            return get_text(language, BotEntity.ADMIN, "infinity_usage")
        if value == 1:
            return get_text(language, BotEntity.ADMIN, "single_usage")
        return str(value)

    @staticmethod
    def _format_optional_limit(value: int | None, language: Language) -> str:
        if not value:
            return get_text(language, BotEntity.ADMIN, "infinity_usage")
        return str(value)

    @staticmethod
    def _format_optional_money(value: float | None) -> str:
        if value is None or value <= 0:
            return "Không giới hạn"
        return f"{config.CURRENCY.get_localized_symbol()}{value:,.0f}"

    @staticmethod
    async def get_coupon_management_menu(language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        kb_builder.button(
            text=get_text(language, BotEntity.ADMIN, "create_new_coupon"),
            callback_data=CouponManagementCallback.create(level=1)
        )
        kb_builder.button(
            text=get_text(language, BotEntity.ADMIN, "view_all_coupons"),
            callback_data=CouponManagementCallback.create(level=5)
        )
        kb_builder.button(
            text=get_text(language, BotEntity.COMMON, "back_button"),
            callback_data=AdminMenuCallback.create(0)
        )
        kb_builder.adjust(1)
        return get_text(language, BotEntity.ADMIN, "coupons_management"), kb_builder

    @staticmethod
    async def coupon_creation_get_type_of_coupon_picker(callback_data: CouponManagementCallback,
                                                        language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        for coupon_type in CouponType:
            kb_builder.button(
                text=coupon_type.get_localized(language),
                callback_data=CouponManagementCallback.create(level=callback_data.level + 1, coupon_type=coupon_type)
            )
        kb_builder.adjust(1)
        kb_builder.row(callback_data.get_back_button(language))
        return get_text(language, BotEntity.ADMIN, "pick_type_of_coupon"), kb_builder

    @staticmethod
    async def coupon_creation_get_number_of_uses_picker(callback_data: CouponManagementCallback,
                                                        language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        for coupon_number_of_use in CouponNumberOfUses:
            kb_builder.button(
                text=coupon_number_of_use.get_localized(language),
                callback_data=CouponManagementCallback.create(level=callback_data.level + 1,
                                                              coupon_type=callback_data.coupon_type,
                                                              number_of_uses=coupon_number_of_use)
            )
        kb_builder.adjust(1)
        kb_builder.row(callback_data.get_back_button(language))
        return get_text(language, BotEntity.ADMIN, "pick_usage_number"), kb_builder

    @staticmethod
    async def request_coupon_value(callback_data: CouponManagementCallback,
                                   state: FSMContext,
                                   language: Language) -> tuple[str, InlineKeyboardBuilder]:
        kb_builder = InlineKeyboardBuilder()
        await state.set_state(CouponsManagementStates.coupon_value)
        await state.update_data(coupon_type=callback_data.coupon_type,
                                number_of_uses=callback_data.number_of_uses)
        kb_builder.button(text=get_text(language, BotEntity.COMMON, "cancel"),
                          callback_data=CouponManagementCallback.create(0))
        return get_text(language, BotEntity.ADMIN, "request_coupon_value").format(
            coupon_type=callback_data.coupon_type.get_localized(language),
            number_of_uses=callback_data.number_of_uses.get_localized(language),
            currency_text=config.CURRENCY.get_localized_text()
        ), kb_builder

    @staticmethod
    async def _request_payment_scope_picker(language: Language) -> InlineKeyboardBuilder:
        kb_builder = InlineKeyboardBuilder()
        for payment_scope in CouponPaymentScope:
            kb_builder.button(
                text=payment_scope.get_localized(language),
                callback_data=CouponManagementCallback.create(level=4, payment_scope=payment_scope)
            )
        kb_builder.adjust(1)
        return kb_builder

    @staticmethod
    async def receive_coupon_value(message: Message,
                                   state: FSMContext,
                                   language: Language) -> tuple[str, InlineKeyboardBuilder]:
        state_data = await state.get_data()
        await NotificationService.edit_reply_markup(message.bot, state_data['chat_id'], state_data['msg_id'])
        coupon_type = CouponType(state_data['coupon_type'])
        number_of_uses = CouponNumberOfUses(state_data['number_of_uses'])
        kb_builder = InlineKeyboardBuilder()
        current_state = await state.get_state()
        cancel_button = InlineKeyboardButton(
            text=get_text(language, BotEntity.COMMON, "cancel"),
            callback_data=CouponManagementCallback.create(level=0).pack()
        )

        try:
            if current_state == CouponsManagementStates.coupon_value:
                coupon_value = float(message.text)
                if coupon_type == CouponType.PERCENTAGE:
                    assert coupon_value < 100
                await state.set_state(CouponsManagementStates.min_order_amount)
                await state.update_data(**state_data, coupon_value=coupon_value)
                msg = get_text(language, BotEntity.ADMIN, "request_coupon_min_order")
                kb_builder.row(cancel_button)
            elif current_state == CouponsManagementStates.min_order_amount:
                min_order_amount = float(message.text)
                await state.update_data(**state_data, min_order_amount=min_order_amount)
                if coupon_type == CouponType.PERCENTAGE:
                    await state.set_state(CouponsManagementStates.max_discount_amount)
                    msg = get_text(language, BotEntity.ADMIN, "request_coupon_max_discount")
                else:
                    await state.set_state(CouponsManagementStates.usage_limit)
                    msg = get_text(language, BotEntity.ADMIN, "request_coupon_usage_limit")
                kb_builder.row(cancel_button)
            elif current_state == CouponsManagementStates.max_discount_amount:
                max_discount_amount = float(message.text)
                await state.set_state(CouponsManagementStates.usage_limit)
                await state.update_data(**state_data, max_discount_amount=max_discount_amount)
                msg = get_text(language, BotEntity.ADMIN, "request_coupon_usage_limit")
                kb_builder.row(cancel_button)
            elif current_state == CouponsManagementStates.usage_limit:
                usage_limit = int(message.text)
                if usage_limit < 0:
                    raise ValueError
                await state.set_state(CouponsManagementStates.per_user_limit)
                await state.update_data(**state_data, usage_limit=usage_limit)
                msg = get_text(language, BotEntity.ADMIN, "request_coupon_per_user_limit")
                kb_builder.row(cancel_button)
            elif current_state == CouponsManagementStates.per_user_limit:
                per_user_limit = int(message.text)
                if per_user_limit < 0:
                    raise ValueError
                await state.set_state(CouponsManagementStates.payment_scope)
                await state.update_data(**state_data, per_user_limit=per_user_limit)
                kb_builder = await CouponManagementService._request_payment_scope_picker(language)
                kb_builder.row(cancel_button)
                msg = get_text(language, BotEntity.ADMIN, "pick_coupon_payment_scope")
            else:
                await state.update_data(coupon_name=message.html_text)
                await state.set_state()
                state_data = await state.get_data()
                kb_builder.button(
                    text=get_text(language, BotEntity.COMMON, "confirm"),
                    callback_data=CouponManagementCallback.create(
                        level=6,
                        coupon_type=coupon_type,
                        number_of_uses=number_of_uses,
                        payment_scope=CouponPaymentScope(state_data['payment_scope']),
                        confirmation=True
                    )
                )
                kb_builder.row(cancel_button)
                max_discount_amount = float(state_data.get('max_discount_amount', 0) or 0)
                msg = get_text(language, BotEntity.ADMIN, "create_coupon_confirmation").format(
                    coupon_name=message.html_text,
                    coupon_type=coupon_type.get_localized(language),
                    number_of_uses=CouponManagementService._format_usage_limit(int(state_data['usage_limit']), language),
                    coupon_value=state_data['coupon_value'],
                    symbol=config.CURRENCY.get_localized_symbol() if coupon_type == CouponType.FIXED else "%",
                    currency_sym=config.CURRENCY.get_localized_symbol(),
                    min_order_amount=float(state_data.get('min_order_amount', 0) or 0),
                    max_discount_text=CouponManagementService._format_optional_money(max_discount_amount),
                    per_user_limit_text=CouponManagementService._format_optional_limit(int(state_data.get('per_user_limit', 0) or 0), language),
                    payment_scope=CouponPaymentScope(state_data['payment_scope']).get_localized(language)
                )
        except Exception:
            kb_builder.row(cancel_button)
            state_to_message = {
                CouponsManagementStates.coupon_value: "request_coupon_value",
                CouponsManagementStates.min_order_amount: "request_coupon_min_order",
                CouponsManagementStates.max_discount_amount: "request_coupon_max_discount",
                CouponsManagementStates.usage_limit: "request_coupon_usage_limit",
                CouponsManagementStates.per_user_limit: "request_coupon_per_user_limit",
            }
            key = state_to_message.get(current_state, "request_coupon_value")
            if key == "request_coupon_value":
                msg = get_text(language, BotEntity.ADMIN, key).format(
                    coupon_type=coupon_type.get_localized(language),
                    number_of_uses=number_of_uses.get_localized(language),
                    currency_text=config.CURRENCY.get_localized_text()
                )
            else:
                msg = get_text(language, BotEntity.ADMIN, key)
        return msg, kb_builder

    @staticmethod
    async def set_coupon_payment_scope(callback_data: CouponManagementCallback,
                                       state: FSMContext,
                                       language: Language) -> tuple[str, InlineKeyboardBuilder]:
        await state.update_data(payment_scope=callback_data.payment_scope)
        await state.set_state(CouponsManagementStates.coupon_name)
        kb_builder = InlineKeyboardBuilder()
        kb_builder.row(InlineKeyboardButton(text=get_text(language, BotEntity.COMMON, "cancel"),
                                            callback_data=CouponManagementCallback.create(level=0).pack()))
        return get_text(language, BotEntity.ADMIN, "request_coupon_name"), kb_builder

    @staticmethod
    async def create_coupon(callback_data: CouponManagementCallback,
                            state: FSMContext,
                            session: AsyncSession,
                            language: Language) -> tuple[str, InlineKeyboardBuilder]:
        state_data = await state.get_data()
        safe_chars = string.ascii_uppercase.replace('I', '').replace('O', '') + string.digits.replace('0', '').replace('1', '')
        code = ''.join(secrets.choice(safe_chars) for _ in range(12))
        coupon_value = float(state_data['coupon_value'])
        coupon_name = state_data['coupon_name']
        min_order_amount = float(state_data.get('min_order_amount', 0) or 0)
        max_discount_amount = float(state_data.get('max_discount_amount', 0) or 0)
        usage_limit = int(state_data.get('usage_limit', 0) or 0)
        per_user_limit = int(state_data.get('per_user_limit', 0) or 0)
        payment_scope = CouponPaymentScope(state_data.get('payment_scope', CouponPaymentScope.ALL))
        coupon_dto = CouponDTO(
            name=coupon_name,
            code=code,
            type=callback_data.coupon_type,
            value=coupon_value,
            usage_limit=usage_limit,
            min_order_amount=min_order_amount,
            max_discount_amount=max_discount_amount if max_discount_amount > 0 else None,
            per_user_limit=per_user_limit,
            allowed_payment_scope=payment_scope
        )
        coupon_dto = await CouponRepository.create(coupon_dto, session)
        await session_commit(session)
        kb_builder = InlineKeyboardBuilder()
        kb_builder.row(callback_data.get_back_button(language, 0))
        return get_text(language, BotEntity.ADMIN, "coupon_created_successfully").format(
            coupon_name=coupon_name,
            coupon_type=callback_data.coupon_type.get_localized(language),
            number_of_uses=CouponManagementService._format_usage_limit(usage_limit, language),
            coupon_value=coupon_value,
            symbol=config.CURRENCY.get_localized_symbol() if callback_data.coupon_type == CouponType.FIXED else "%",
            currency_sym=config.CURRENCY.get_localized_symbol(),
            min_order_amount=min_order_amount,
            max_discount_text=CouponManagementService._format_optional_money(max_discount_amount),
            per_user_limit_text=CouponManagementService._format_optional_limit(per_user_limit, language),
            payment_scope=payment_scope.get_localized(language),
            use_before=coupon_dto.expire_datetime.strftime("%m/%d/%Y, %I:%M %p"),
            code=coupon_dto.code
        ), kb_builder

    @staticmethod
    async def view_coupons(callback_data: CouponManagementCallback,
                           session: AsyncSession,
                           language: Language) -> tuple[str, InlineKeyboardBuilder]:
        coupons = await CouponRepository.get_paginated(callback_data.page, session)
        kb_builder = InlineKeyboardBuilder()
        for coupon in coupons:
            kb_builder.button(
                text=get_text(language, BotEntity.ADMIN, "coupon").format(name=coupon.name if coupon.name else f"#{coupon.id}"),
                callback_data=CouponManagementCallback.create(level=7, coupon_id=coupon.id)
            )
        kb_builder.adjust(1)
        kb_builder = await add_pagination_buttons(kb_builder,
                                                  callback_data,
                                                  CouponRepository.get_max_page(session),
                                                  callback_data.get_back_button(language, 0), language)
        return get_text(language, BotEntity.ADMIN, "view_all_coupons"), kb_builder

    @staticmethod
    async def view_coupon(callback_data: CouponManagementCallback,
                          session: AsyncSession,
                          language: Language) -> tuple[str, InlineKeyboardBuilder]:
        coupon_dto = await CouponRepository.get_by_id(callback_data.coupon_id, session)

        if callback_data.page == -2 and callback_data.confirmation is True:
            await CouponRepository.delete(coupon_dto.id, session)
            await session_commit(session)
            kb_builder = InlineKeyboardBuilder()
            kb_builder.row(
                InlineKeyboardButton(
                    text=get_text(language, BotEntity.COMMON, "back_button"),
                    callback_data=CouponManagementCallback.create(level=5, page=0).pack()
                )
            )
            return get_text(language, BotEntity.ADMIN, "successfully_deleted").format(
                entity_name=coupon_dto.name if coupon_dto.name else coupon_dto.code,
                entity_to_delete=get_text(language, BotEntity.ADMIN, "coupon_delete_entity")
            ), kb_builder

        if callback_data.page == -2 and callback_data.confirmation is False:
            kb_builder = InlineKeyboardBuilder()
            kb_builder.button(
                text=get_text(language, BotEntity.COMMON, "confirm"),
                callback_data=CouponManagementCallback.create(
                    level=callback_data.level,
                    coupon_id=coupon_dto.id,
                    confirmation=True,
                    page=-2,
                )
            )
            kb_builder.button(
                text=get_text(language, BotEntity.COMMON, "cancel"),
                callback_data=CouponManagementCallback.create(
                    level=callback_data.level,
                    coupon_id=coupon_dto.id,
                )
            )
            kb_builder.row(callback_data.get_back_button(language, 5))
            return get_text(language, BotEntity.ADMIN, "delete_coupon_confirmation").format(
                coupon_name=coupon_dto.name if coupon_dto.name else coupon_dto.code
            ), kb_builder

        if callback_data.page == -1:
            coupon_dto.is_active = not coupon_dto.is_active
            await CouponRepository.update(coupon_dto, session)
            await session_commit(session)
            coupon_dto = await CouponRepository.get_by_id(callback_data.coupon_id, session)

        kb_builder = InlineKeyboardBuilder()
        if coupon_dto.is_active:
            kb_builder.button(
                text=get_text(language, BotEntity.ADMIN, "disable"),
                callback_data=CouponManagementCallback.create(
                    level=callback_data.level,
                    coupon_id=coupon_dto.id,
                    page=-1,
                )
            )
        else:
            kb_builder.button(
                text=get_text(language, BotEntity.ADMIN, "enable"),
                callback_data=CouponManagementCallback.create(
                    level=callback_data.level,
                    coupon_id=coupon_dto.id,
                    page=-1,
                )
            )
        kb_builder.button(
            text=get_text(language, BotEntity.ADMIN, "delete_coupon"),
            callback_data=CouponManagementCallback.create(
                level=callback_data.level,
                coupon_id=coupon_dto.id,
                confirmation=False,
                page=-2,
            )
        )
        kb_builder.adjust(1)
        kb_builder.row(callback_data.get_back_button(language, 5))
        return get_text(language, BotEntity.ADMIN, "coupon_info").format(
            coupon_name=coupon_dto.name,
            is_active=coupon_dto.is_active,
            coupon_type=coupon_dto.type.get_localized(language),
            number_of_uses=CouponManagementService._format_usage_limit(coupon_dto.usage_limit, language),
            coupon_value=float(coupon_dto.value),
            symbol=config.CURRENCY.get_localized_symbol() if coupon_dto.type == CouponType.FIXED else "%",
            currency_sym=config.CURRENCY.get_localized_symbol(),
            min_order_amount=float(coupon_dto.min_order_amount),
            max_discount_text=CouponManagementService._format_optional_money(float(coupon_dto.max_discount_amount) if coupon_dto.max_discount_amount is not None else None),
            per_user_limit_text=CouponManagementService._format_optional_limit(coupon_dto.per_user_limit, language),
            payment_scope=coupon_dto.allowed_payment_scope.get_localized(language),
            start_datetime=coupon_dto.start_datetime.strftime("%m/%d/%Y, %I:%M %p"),
            use_before=coupon_dto.expire_datetime.strftime("%m/%d/%Y, %I:%M %p"),
            code=coupon_dto.code,
            usage_count=coupon_dto.usage_count
        ), kb_builder
