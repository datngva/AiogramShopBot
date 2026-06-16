"""add pinned product metadata to items

Revision ID: c1a4f8b2d901
Revises: 91c3856a8aa0
Create Date: 2026-06-16 13:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a4f8b2d901'
down_revision: Union[str, None] = '91c3856a8aa0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("pin_group", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("pin_label", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("pin_priority", sa.Integer(), nullable=False, server_default="999"))


def downgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("pin_priority")
        batch_op.drop_column("pin_label")
        batch_op.drop_column("pin_group")
        batch_op.drop_column("is_pinned")
