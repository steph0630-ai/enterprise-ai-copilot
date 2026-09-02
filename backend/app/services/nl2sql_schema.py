"""NL2SQL 动态 schema 读取（Day 26 通用化）

背景：query_data 工具原本在 description 里写死 orders 表结构，换任何真实库都要改代码。
这里用 SQLAlchemy inspect(engine) 运行时读授权表（settings.NL2SQL_ALLOWED_TABLES）的真实列，
拼成给模型看的"表结构"描述段——加/换表只改配置，不改代码。

安全边界：只"读结构"给模型看，不放开查询——模型能看清授权表长啥样，
但能碰哪些表仍由 NL2SQL_ALLOWED_TABLES 显式授权（敏感表绝不入列）。

为什么不止一个函数：get_schema_text() 是给 build_tools 用的入口；
_schema_for_tables 用 lru_cache 按"表清单"缓存——同一配置只读一次库，幂等。
若某张表结构变了，invalidate_schema() 清缓存即可（暂无触发点，表结构变更属运维操作）。
"""

from functools import lru_cache

from sqlalchemy import inspect

from app.core.config import settings
from app.database.session import engine


def _read_columns(table: str) -> list[tuple[str, str]]:
    """读一张表的列，返回 [(列名, 类型字符串), ...]

    类型字符串如 "INTEGER"、"VARCHAR(50)"、"DECIMAL(10, 2)"、"DATETIME"。"""
    insp = inspect(engine)
    return [(c["name"], str(c["type"])) for c in insp.get_columns(table)]


@lru_cache(maxsize=None)
def _schema_for_tables(tables: tuple[str, ...]) -> str:
    """按表清单生成 schema 描述段；单表读失败跳过（不拖垮整个描述）。

    列描述 = 列名 + 类型 +（字段语义注释，来自 settings.NL2SQL_COLUMN_COMMENTS）。
    语义注释让模型生成 SQL 时知道列的业务含义（如 department 是州代码），
    避免它靠猜把 'SP州' 硬拼进去。
    """
    parts = []
    comments = settings.NL2SQL_COLUMN_COMMENTS
    for t in tables:
        try:
            cols = _read_columns(t)
        except Exception as e:  # 表不存在/无权限——跳过，不因一张表废掉整个工具描述
            parts.append(f"表 {t}(读取失败：{e})")
            continue
        col_comments = comments.get(t, {})
        col_str = ", ".join(
            f"{name} {ctype}" + (f"（{col_comments[name]}）" if name in col_comments else "")
            for name, ctype in cols
        )
        parts.append(f"表 {t}({col_str})")
    return "\n".join(parts)


def get_schema_text() -> str:
    """读当前授权表的真实结构，拼成给模型的描述段。"""
    return _schema_for_tables(tuple(settings.NL2SQL_ALLOWED_TABLES))


def invalidate_schema() -> None:
    """表结构变更后清缓存（运维/测试用）。"""
    _schema_for_tables.cache_clear()
