from datetime import datetime

from pydantic import BaseModel
from sqladmin import ModelView
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship

from enums.bank_payment_status import BankPaymentStatus
from models.base import Base


class BankPayment(Base):
    __tablename__ = "bank_payments"

    id = Column(Integer, primary_key=True)
    buy_id = Column(Integer, ForeignKey("buys.id", ondelete="CASCADE"), nullable=False)
    buy = relationship("Buy")
    provider = Column(String, nullable=False, default="SEPAY")
    payment_code = Column(String, nullable=False, unique=True, index=True)
    expected_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, nullable=True)
    status = Column(Enum(BankPaymentStatus), nullable=False, default=BankPaymentStatus.PENDING)
    sepay_transaction_id = Column(String, nullable=True, unique=True)
    raw_payload = Column(String, nullable=True)
    payment_type = Column(String, nullable=False, default="FULL")
    order_total_amount = Column(Float, nullable=True)
    remaining_amount = Column(Float, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class BankPaymentDTO(BaseModel):
    id: int | None = None
    buy_id: int
    provider: str = "SEPAY"
    payment_code: str
    expected_amount: float
    paid_amount: float | None = None
    status: BankPaymentStatus = BankPaymentStatus.PENDING
    sepay_transaction_id: str | None = None
    raw_payload: str | None = None
    payment_type: str = "FULL"
    order_total_amount: float | None = None
    remaining_amount: float | None = None
    expires_at: datetime
    paid_at: datetime | None = None
    created_at: datetime | None = None


class BankPaymentAdmin(ModelView, model=BankPayment):
    column_exclude_list = [BankPayment.raw_payload]
    column_sortable_list = [BankPayment.id, BankPayment.buy_id, BankPayment.payment_code,
                            BankPayment.expected_amount, BankPayment.paid_amount,
                            BankPayment.status, BankPayment.payment_type,
                            BankPayment.created_at, BankPayment.paid_at]
    column_searchable_list = [BankPayment.payment_code, BankPayment.sepay_transaction_id]
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True
