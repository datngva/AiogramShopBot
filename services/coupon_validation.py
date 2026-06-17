from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from enums.coupon_payment_scope import CouponPaymentScope
from enums.coupon_type import CouponType
from repositories.coupon import CouponUsageRepository
from services.sepay import SePayService


class CouponValidationErrorCode(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    NOT_ACTIVE = "NOT_ACTIVE"
    NOT_STARTED = "NOT_STARTED"
    EXPIRED = "EXPIRED"
    USAGE_LIMIT_REACHED = "USAGE_LIMIT_REACHED"
    USER_LIMIT_REACHED = "USER_LIMIT_REACHED"
    MIN_ORDER_NOT_REACHED = "MIN_ORDER_NOT_REACHED"
    PAYMENT_SCOPE_NOT_ALLOWED = "PAYMENT_SCOPE_NOT_ALLOWED"


@dataclass
class CouponValidationResult:
    is_valid: bool
    coupon: object | None = None
    discount_amount: float = 0.0
    final_total: float = 0.0
    error_code: CouponValidationErrorCode | None = None


class CouponValidationService:
    @staticmethod
    def _to_float(value) -> float:
        if isinstance(value, Decimal):
            return float(value)
        return float(value or 0)

    @staticmethod
    def _is_payment_scope_allowed(payment_scope: CouponPaymentScope, payment_type: str | None) -> bool:
        if payment_scope == CouponPaymentScope.ALL:
            return True
        is_deposit = payment_type == SePayService.PAYMENT_TYPE_DEPOSIT
        if payment_scope == CouponPaymentScope.FULL_ONLY:
            return not is_deposit
        if payment_scope == CouponPaymentScope.EXCLUDE_DEPOSIT:
            return not is_deposit
        return True

    @staticmethod
    async def validate_coupon(coupon,
                              cart_total_price: float,
                              user_id: int,
                              session: AsyncSession,
                              payment_type: str | None = None) -> CouponValidationResult:
        if coupon is None:
            return CouponValidationResult(is_valid=False, error_code=CouponValidationErrorCode.NOT_FOUND)
        if coupon.is_active is False:
            return CouponValidationResult(is_valid=False, coupon=coupon,
                                          error_code=CouponValidationErrorCode.NOT_ACTIVE)
        usage_limit = int(coupon.usage_limit or 0)
        usage_count = int(coupon.usage_count or 0)
        if usage_limit > 0 and usage_count >= usage_limit:
            return CouponValidationResult(is_valid=False, coupon=coupon,
                                          error_code=CouponValidationErrorCode.USAGE_LIMIT_REACHED)
        per_user_limit = int(coupon.per_user_limit or 0)
        if per_user_limit > 0:
            current_user_usage_count = await CouponUsageRepository.count_by_coupon_and_user(coupon.id, user_id, session)
            if current_user_usage_count >= per_user_limit:
                return CouponValidationResult(is_valid=False, coupon=coupon,
                                              error_code=CouponValidationErrorCode.USER_LIMIT_REACHED)
        min_order_amount = CouponValidationService._to_float(coupon.min_order_amount)
        if cart_total_price < min_order_amount:
            return CouponValidationResult(is_valid=False, coupon=coupon,
                                          error_code=CouponValidationErrorCode.MIN_ORDER_NOT_REACHED)
        payment_scope = coupon.allowed_payment_scope or CouponPaymentScope.ALL
        if not CouponValidationService._is_payment_scope_allowed(payment_scope, payment_type):
            return CouponValidationResult(is_valid=False, coupon=coupon,
                                          error_code=CouponValidationErrorCode.PAYMENT_SCOPE_NOT_ALLOWED)

        coupon_value = CouponValidationService._to_float(coupon.value)
        if coupon.type == CouponType.PERCENTAGE:
            discount_amount = (coupon_value / 100) * cart_total_price
            max_discount_amount = coupon.max_discount_amount
            if max_discount_amount is not None:
                discount_amount = min(discount_amount, CouponValidationService._to_float(max_discount_amount))
        else:
            discount_amount = coupon_value
        final_total = max(cart_total_price - discount_amount, 1)
        actual_discount = max(cart_total_price - final_total, 0)
        return CouponValidationResult(is_valid=True,
                                      coupon=coupon,
                                      discount_amount=actual_discount,
                                      final_total=final_total)
