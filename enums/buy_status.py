from enum import Enum

from enums.bot_entity import BotEntity
from enums.language import Language
from utils.utils import get_text


class BuyStatus(Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    DEPOSIT_PAID = "DEPOSIT_PAID"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    REFUNDED = "REFUNDED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    PAYMENT_FAILED = "PAYMENT_FAILED"

    def get_localized(self, language: Language):
        return get_text(language, BotEntity.COMMON, self.value.lower())
