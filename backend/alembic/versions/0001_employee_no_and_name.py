"""Day 13：登录账号 username → 工号 employee_no，并新增姓名 name 列

为什么这个迁移是"第一个"（down_revision = None）？
- 项目从 Day 1 到现在一直用 create_tables.py 建表，从没用过迁移工具；
- 现在引入 Alembic，这份迁移记录"从旧结构到新结构"的第一个变化；
- 注意：这里只记录"变化"，不重演建表。老表已经存在，直接改名+加列。

为什么改名要手写，不用 autogenerate？
- autogenerate 只对比"模型 vs 数据库"看存在性：username 没了、employee_no 出现，
  会被当成"删列 + 加列"，删列会连数据一起丢掉；
- 所以改列名必须手写 op.alter_column（指定 new_column_name）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """旧(username) → 新(employee_no + name)"""

    # 1) 先摘掉旧列名上的唯一索引（否则 MySQL 改名后索引名还是 ix_users_username，
    #    和新库 create_tables 生成的 ix_users_employee_no 不一致）
    op.drop_index("ix_users_username", table_name="users")

    # 2) 改列名：username → employee_no（数据原样保留）
    #    坑：MySQL 的 CHANGE COLUMN 必须带完整列定义，
    #    所以这里要显式给 existing_type/existing_nullable，否则报
    #    "All MySQL CHANGE/MODIFY COLUMN operations require the existing type."
    op.alter_column(
        "users",
        "username",
        new_column_name="employee_no",
        existing_type=sa.String(50),
        existing_nullable=False,
    )

    # 3) 新建唯一索引，名字对应新列名
    op.create_index("ix_users_employee_no", "users", ["employee_no"], unique=True)

    # 4) 加姓名列：NOT NULL 但给个空字符串默认值，好让老数据能插进去
    op.add_column(
        "users",
        sa.Column("name", sa.String(50), nullable=False, server_default=""),
    )

    # 5) 给老用户补姓名：先用工号当占位姓名，回头种子脚本会覆盖成真名
    op.execute("UPDATE users SET name = employee_no")


def downgrade() -> None:
    """新(employee_no + name) → 旧(username)：把上面的步骤倒着撤"""

    # 1) 摘掉新索引
    op.drop_index("ix_users_employee_no", table_name="users")

    # 2) 撤姓名列
    op.drop_column("users", "name")

    # 3) 改回列名
    op.alter_column("users", "employee_no", new_column_name="username")

    # 4) 还原旧索引
    op.create_index("ix_users_username", "users", ["username"], unique=True)
