"""容器启动入口（Day 17 创建 / Day 18 修一个 stamp 坑）

一个 python 脚本按顺序完成启动前的所有事：
    等数据库就绪 → （全新库建表并 stamp | 老库 upgrade）→ 种子数据 → 起 uvicorn

为什么用 python 写入口而不是 shell 脚本？
- Windows 上写的 .sh 容易带 CRLF 换行，进 Linux 容器会报 "command not found"；
- python 脚本跨平台无这个坑。

为什么全新库 stamp、老库 upgrade（Day 18 教训）？
- 全新库：create_tables.py 已建出"当前最新结构"的表，迁移 0001/0002 是对旧结构的
  历史改造，对新库没有意义 → 直接 stamp 标记"已应用"，让 alembic_version 对得上。
- 老库：有 alembic_version 表 = 有迁移历史 → 必须 upgrade，把还没跑过的迁移补上。
- 原来无条件 stamp 的坑：老库重建容器时，stamp 把新迁移"假标记"成已应用，
  实际列没加（0002 的 error_message 就这么漏过，上传 500 Unknown column）。
  这就是"在已有项目引入 Alembic"的收尾动作：老库 upgrade，新库 stamp。
"""

import os
import subprocess
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import settings


def wait_for_db(retries: int = 30, delay: int = 2) -> None:
    """MySQL 容器起来 ≠ 能连。用 SQLAlchemy 发 SELECT 1，直到成功或超时。"""
    print("等待数据库就绪...")
    for i in range(retries):
        try:
            engine = create_engine(settings.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("数据库就绪")
            return
        except Exception as e:  # noqa: BLE001  # 数据库没起来会抛连接异常
            print(f"  ({i + 1}/{retries}) {type(e).__name__}: 还没就绪，重试")
            time.sleep(delay)
    raise SystemExit("数据库 60 秒内没就绪，退出")


def run(cmd: list[str]) -> None:
    """跑一个子命令，失败立刻退出（check=True 抛异常 → 容器重启）"""
    print(f"> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def is_fresh_db() -> bool:
    """判断是全新库还是已有库：看 alembic_version 表在不在

    全新库（或从未被迁移工具管过的老库）→ 没有这张表 → 用 stamp；
    已有迁移历史的库 → 有这张表 → 用 upgrade。
    """
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'alembic_version'"
            )
        ).scalar()
    return n == 0


if __name__ == "__main__":
    wait_for_db()

    # Day 18 修的一个真坑：原来无条件 stamp head，老库会被"假标记"成已应用，
    # 实际迁移没跑（0002 的 error_message 列就是这么漏掉的）。
    # 现在区分：全新库 stamp（表已是当前结构，迁移只是历史标记）；
    #           老库 upgrade（由迁移创建新表、添加新列，不能提前 create_all）。
    if is_fresh_db():
        run([sys.executable, "create_tables.py"])
        run([sys.executable, "-m", "alembic", "stamp", "head"])
    else:
        run([sys.executable, "-m", "alembic", "upgrade", "head"])

    run([sys.executable, "scripts/seed_users.py"])              # E001-003 演示账号
    # Day 25.3：seed_orders 已删除——假订单数据库整个不要，等 Olist 真实数据导入时重建

    # 用 exec 把自己替换成 uvicorn：让 uvicorn 成为 PID 1，
    # Docker 停容器发 SIGTERM 时能直接送达（优雅关闭，而不是被硬杀）
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])
