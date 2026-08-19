"""容器启动入口（Day 17）

一个 python 脚本按顺序完成启动前的所有事：
    等数据库就绪 → 建表 → alembic stamp → 种子数据 → 起 uvicorn

为什么用 python 写入口而不是 shell 脚本？
- Windows 上写的 .sh 容易带 CRLF 换行，进 Linux 容器会报 "command not found"；
- python 脚本跨平台无这个坑。

为什么 alembic stamp head 而不是 upgrade head？
- 容器里是（或可能是）全新库，create_tables.py 已经建出"当前最新结构"的表；
- 迁移 0001 是历史遗留的"从旧结构到新结构"，对新库没有意义（表已是新结构），
  直接 stamp 标记"已应用"，让 alembic_version 对得上即可。
- 这也是"在已有项目引入 Alembic"的收尾动作：老库 upgrade，新库 stamp。
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


if __name__ == "__main__":
    wait_for_db()
    run([sys.executable, "create_tables.py"])                    # 建表（幂等：只建不存在的）
    run([sys.executable, "-m", "alembic", "stamp", "head"])     # 标记迁移已应用
    run([sys.executable, "scripts/seed_users.py"])              # E001-003 演示账号
    run([sys.executable, "scripts/seed_orders.py"])             # 7 条订单（已存在则跳过）

    # 用 exec 把自己替换成 uvicorn：让 uvicorn 成为 PID 1，
    # Docker 停容器发 SIGTERM 时能直接送达（优雅关闭，而不是被硬杀）
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])
