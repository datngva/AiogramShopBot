from enum import Enum

from enums.bot_entity import BotEntity
from enums.language import Language
from utils.utils import get_text


class CouponPaymentScope(str, Enum):
    ALL = "ALL"
    FULL_ONLY = "FULL_ONLY"
    EXCLUDE_DEPOSIT = "EXCLUDE_DEPOSIT"

    def get_localized(self, language: Language) -> str:
        return get_text(language, BotEntity.ADMIN, f"coupon_payment_scope_{self.value.lower()}")

    def __str__(self):
        return self.value
