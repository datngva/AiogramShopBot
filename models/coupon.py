from datetime import datetime, timezone, timedelta

from pydantic import BaseModel
from sqladmin import ModelView
from sqlalchemy import Column, DateTime, Enum, Boolean, String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from enums.coupon_payment_scope import CouponPaymentScope
from enums.coupon_type import CouponType
from models.base import Base


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=True)
    code = Column(String(12), unique=True, nullable=False, index=True)
    type = Column(Enum(CouponType), nullable=False)
    value = Column(Numeric(10, 2), nullable=False)
    create_datetime = Column(DateTime(timezone=True), nullable=False)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    expire_datetime = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, default=1)
    usage_count = Column(Integer, default=0)
    min_order_amount = Column(Numeric(10, 2), nullable=False, default=0)
    max_discount_amount = Column(Numeric(10, 2), nullable=True)
    per_user_limit = Column(Integer, nullable=False, default=0)
    allowed_payment_scope = Column(Enum(CouponPaymentScope), nullable=False, default=CouponPaymentScope.ALL)
    buys = relationship("Buy", back_populates="coupon")
    usages = relationship("CouponUsage", back_populates="coupon", cascade="all, delete-orphan")

    def __repr__(self):
        return f"Coupon: {self.name}"


class CouponUsage(Base):
    __tablename__ = "coupon_usages"
    __table_args__ = (
        UniqueConstraint("coupon_id", "buy_id", name="uq_coupon_usages_coupon_buy"),
    )

    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    buy_id = Column(Integer, ForeignKey("buys.id", ondelete="CASCADE"), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    coupon = relationship("Coupon", back_populates="usages")
    user = relationship("User")
    buy = relationship("Buy")


class CouponDTO(BaseModel):
    id: int | None = None
    name: str | None = None
    code: str | None = None
    type: CouponType | None = None
    value: float | None = None
    create_datetime: datetime = datetime.now(tz=timezone.utc)
    start_datetime: datetime = datetime.now(tz=timezone.utc)
    expire_datetime: datetime = datetime.now(tz=timezone.utc) + timedelta(days=30)
    is_active: bool = True
    usage_limit: int = 1
    usage_count: int = 0
    min_order_amount: float = 0.0
    max_discount_amount: float | None = None
    per_user_limit: int = 0
    allowed_payment_scope: CouponPaymentScope = CouponPaymentScope.ALL


class CouponUsageDTO(BaseModel):
    id: int | None = None
    coupon_id: int
    user_id: int
    buy_id: int
    used_at: datetime = datetime.now(tz=timezone.utc)


class CouponAdmin(ModelView, model=Coupon):
    name = "Coupon"
    name_plural = "Coupons"
    column_exclude_list = [Coupon.buys, Coupon.usages]
    column_searchable_list = [Coupon.name, Coupon.code]
    column_sortable_list = [Coupon.id,
                            Coupon.name,
                            Coupon.code,
                            Coupon.type,
                            Coupon.value,
                            Coupon.create_datetime,
                            Coupon.start_datetime,
                            Coupon.expire_datetime,
                            Coupon.is_active,
                            Coupon.usage_limit,
                            Coupon.usage_count,
                            Coupon.min_order_amount,
                            Coupon.max_discount_amount,
                            Coupon.per_user_limit,
                            Coupon.allowed_payment_scope]
    can_edit = True
    can_create = True
    can_delete = False
    can_export = False
