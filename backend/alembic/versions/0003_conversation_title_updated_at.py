"""Day 24：conversations 表加 title、updated_at 两列（会话列表侧边栏）

为什么加这两列：
- title：侧边栏要显示会话名。老会话没标题 → 可空，前端兜底"未命名对话"。
- updated_at：列表要按"最后活动"排序。之前只有 created_at，没法把
  "刚聊完的会话"排到"一周前的会话"前面。

server_default 要和模型声明写一致（Day 13 phone 唯一索引漂移的教训）：
create_all 新建的库带 DEFAULT，迁移加的列也要带，否则两套库结构不一样。
onupdate 是 SQLAlchemy ORM 层行为，不进 DDL，这里只写 server_default。

老库 upgrade、新库 stamp 由 docker-entrypoint.py 处理（Day 18 已修好），本机跑
`alembic upgrade head` 即可补列。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加两列（都可空，老会话没有标题/未知活动时间）"""
    op.add_column(
        "conversations",
        sa.Column("title", sa.String(200), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """撤销：把两列删掉"""
    op.drop_column("conversations", "updated_at")
    op.drop_column("conversations", "title")
