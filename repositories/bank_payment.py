from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db import session_execute, session_flush
from models.bank_payment import BankPayment, BankPaymentDTO


class BankPaymentRepository:
    @staticmethod
    async def create(payment_dto: BankPaymentDTO, session: AsyncSession | Session) -> BankPaymentDTO:
        payment = BankPayment(**payment_dto.model_dump(exclude={"id", "created_at"}))
        session.add(payment)
        await session_flush(session)
        return BankPaymentDTO.model_validate(payment, from_attributes=True)

    @staticmethod
    async def get_by_payment_code(payment_code: str, session: AsyncSession | Session) -> BankPaymentDTO | None:
        result = await session_execute(select(BankPayment).where(BankPayment.payment_code == payment_code), session)
        payment = result.scalar_one_or_none()
        return BankPaymentDTO.model_validate(payment, from_attributes=True) if payment else None

    @staticmethod
    async def get_model_by_payment_code(payment_code: str, session: AsyncSession | Session) -> BankPayment | None:
        result = await session_execute(select(BankPayment).where(BankPayment.payment_code == payment_code), session)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_transaction_id(transaction_id: str, session: AsyncSession | Session) -> BankPaymentDTO | None:
        result = await session_execute(select(BankPayment).where(BankPayment.sepay_transaction_id == transaction_id), session)
        payment = result.scalar_one_or_none()
        return BankPaymentDTO.model_validate(payment, from_attributes=True) if payment else None
