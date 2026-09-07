"""NL2SQL 通用化测试（Day 26）

背景：query_data 原本只能查写死的一张 orders 表。通用化后：
- 能查的表由 settings.NL2SQL_ALLOWED_TABLES 配置(加/换表只改配置)；
- 表结构从数据库运行时读取，注入工具描述(build_tools)；
- 安全底线：子查询/JOIN/多表/注释/单条 SELECT 的结构限制原样保留。

原则：全打桩,不碰真实数据库(_validate_query_scope 纯字符串;build_tools 的
schema 注入用 monkeypatch 换掉 get_schema_text,避免连库)。
"""

import app.agent.tools as tools
from app.agent.tools import build_tools, _validate_query_scope


def _qdata_desc():
    return [t for t in build_tools() if t["function"]["name"] == "query_data"][0]["function"]["description"]


def test_scope_allows_configured_tables(monkeypatch):
    """配置里的多张业务表都能查"""
    monkeypatch.setattr(tools.settings, "NL2SQL_ALLOWED_TABLES", ["orders", "products"])
    assert _validate_query_scope("SELECT amount FROM orders") is None
    assert _validate_query_scope("SELECT name FROM products") is None


def test_scope_can_use_employee_scoped_table():
    assert (
        _validate_query_scope(
            "SELECT SUM(amount) FROM scoped_orders", {"scoped_orders"}
        )
        is None
    )
    assert _validate_query_scope("SELECT SUM(amount) FROM orders", {"scoped_orders"})


def test_scope_rejects_non_whitelisted(monkeypatch):
    """非白名单表(users)被拒——敏感表绝不入列"""
    monkeypatch.setattr(tools.settings, "NL2SQL_ALLOWED_TABLES", ["orders"])
    err = _validate_query_scope("SELECT hashed_password FROM users")
    assert err is not None and "业务表" in err


def test_scope_still_blocks_join_and_subquery(monkeypatch):
    """通用化后,子查询/JOIN 机制不变——不能变成自由表读取器"""
    monkeypatch.setattr(tools.settings, "NL2SQL_ALLOWED_TABLES", ["orders", "products"])
    assert _validate_query_scope("SELECT (SELECT COUNT(*) FROM users) FROM orders") is not None
    assert _validate_query_scope("SELECT * FROM orders o JOIN products p ON o.id=p.id") is not None


def test_build_tools_injects_live_schema(monkeypatch):
    """build_tools 把 __SCHEMA__ 占位替换为真实表结构,不留占位符"""
    monkeypatch.setattr(tools, "get_schema_text", lambda: "表 orders(id INTEGER, status VARCHAR)")
    desc = _qdata_desc()
    assert "表 orders(id INTEGER, status VARCHAR)" in desc
    assert "__SCHEMA__" not in desc


def test_build_tools_keeps_tool_boundary_wording(monkeypatch):
    """描述仍保留工具边界措辞(文档数据转 search_knowledge)"""
    monkeypatch.setattr(tools, "get_schema_text", lambda: "")
    desc = _qdata_desc()
    assert "系统数据库中的业务表" in desc
    assert "search_knowledge" in desc
