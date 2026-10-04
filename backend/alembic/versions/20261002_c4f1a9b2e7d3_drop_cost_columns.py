"""drop cost columns

项目可能要接第三方中转，模型名和单价都不在我们控制内，维护价目表只会持续给出
错误的数字，所以不再折算金额。token 统计保留——它是厂商无关且始终可靠的。

Revision ID: c4f1a9b2e7d3
Revises: 8b887c4c07df
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4f1a9b2e7d3"
down_revision: str | None = "8b887c4c07df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("spans", "cost")
    op.drop_column("traces", "total_cost")


def downgrade() -> None:
    op.add_column("spans", sa.Column("cost", sa.Numeric(12, 6), nullable=True))
    op.add_column("traces", sa.Column("total_cost", sa.Numeric(12, 6), nullable=True))
