from enum import Enum


class BankPaymentStatus(Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    UNDERPAID = "UNDERPAID"
    EXPIRED = "EXPIRED"
    UNMATCHED = "UNMATCHED"
    FAILED = "FAILED"
