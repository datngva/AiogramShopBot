"""coupon v2 fields and usage tracking

Revision ID: 3f2d6c91b7aa
Revises: c1a4f8b2d901
Create Date: 2026-06-17 13:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f2d6c91b7aa'
down_revision: Union[str, None] = 'c1a4f8b2d901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


couponpaymentscope = sa.Enum('ALL', 'FULL_ONLY', 'EXCLUDE_DEPOSIT', name='couponpaymentscope')


def upgrade() -> None:
    couponpaymentscope.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('coupons') as batch_op:
        batch_op.add_column(sa.Column('start_datetime', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('min_order_amount', sa.Numeric(10, 2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('max_discount_amount', sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('per_user_limit', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('allowed_payment_scope', couponpaymentscope, nullable=False, server_default='ALL'))

    op.execute("UPDATE coupons SET start_datetime = create_datetime WHERE start_datetime IS NULL")

    with op.batch_alter_table('coupons') as batch_op:
        batch_op.alter_column('start_datetime', existing_type=sa.DateTime(timezone=True), nullable=False)

    op.create_table(
        'coupon_usages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('coupon_id', sa.Integer(), sa.ForeignKey('coupons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('buy_id', sa.Integer(), sa.ForeignKey('buys.id', ondelete='CASCADE'), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('coupon_id', 'buy_id', name='uq_coupon_usages_coupon_buy')
    )
    op.create_index(op.f('ix_coupon_usages_coupon_id'), 'coupon_usages', ['coupon_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_user_id'), 'coupon_usages', ['user_id'], unique=False)
    op.create_index(op.f('ix_coupon_usages_buy_id'), 'coupon_usages', ['buy_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_coupon_usages_buy_id'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_user_id'), table_name='coupon_usages')
    op.drop_index(op.f('ix_coupon_usages_coupon_id'), table_name='coupon_usages')
    op.drop_table('coupon_usages')

    with op.batch_alter_table('coupons') as batch_op:
        batch_op.drop_column('allowed_payment_scope')
        batch_op.drop_column('per_user_limit')
        batch_op.drop_column('max_discount_amount')
        batch_op.drop_column('min_order_amount')
        batch_op.drop_column('start_datetime')

    couponpaymentscope.drop(op.get_bind(), checkfirst=True)
