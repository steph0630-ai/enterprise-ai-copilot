"""Day 18：documents 表加 error_message 列（后台异步入库失败时记录原因）

为什么这个迁移只是"加一列"？
- 异步入库引入了 failed 状态，失败时要把原因存下来，前端才能显示"为什么失败"。
- status 列本来就是个字符串（没有枚举约束），新增的 uploading/processing/failed
  不需要动表结构，只有 error_message 需要一列。

注意：create_tables.py 的 create_all 只会建"不存在的表"，
对已经存在的表不会加列。所以跑着的库要靠 `alembic upgrade head` 补列——
"老库 upgrade、新库 stamp" 又一次验证（面试题 #74）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加 error_message 列（可空——老文档没失败，本来就是 NULL）"""
    op.add_column(
        "documents",
        sa.Column("error_message", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """撤销：把列删掉"""
    op.drop_column("documents", "error_message")
