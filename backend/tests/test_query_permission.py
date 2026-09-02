"""部门数据权限测试（Day 17 回归）

背景：Day 15 加了 super_admin 角色，但 tools.py 的部门校验还只认 admin，
导致超管被当成普通员工（部门 None → 永远被告知"只能查部门(None)"）。
这组测试把修复钉死：管理端（admin/super_admin）可查全部部门，员工只能查本部门。
"""

from types import SimpleNamespace

from app.agent.tools import _query_data, build_tools
from app.models.order import Order  # 必须在 create_all 前导入，orders 表才会建


def make_user(role, department=None):
    """造一个假的 user 对象（_query_data/build_tools 只用到 role 和 department）"""
    return SimpleNamespace(role=role, department=department)


# ========== 工具说明书：权限描述 ==========

def test_build_tools_super_admin_no_dept_restriction():
    """超管的 query_data 说明书不该有"只能查本部门"（回归点）"""
    desc = build_tools(make_user("super_admin"))[1]["function"]["description"]
    assert "只能查询本部门" not in desc


def test_build_tools_employee_has_dept_restriction():
    """员工的说明书会写死部门条件"""
    desc = build_tools(make_user("employee", "销售一部"))[1]["function"]["description"]
    assert "销售一部" in desc


# ========== 实际执行：部门校验 ==========

def seed_orders(db_session):
    db_session.add_all(
        [
            Order(department="销售一部", amount=100),
            Order(department="市场部", amount=200),
        ]
    )
    db_session.commit()


def test_super_admin_can_query_any_department(db_session):
    """超管查"全部订单"（不带部门条件）→ 放行（回归点：原来返回权限不足）"""
    seed_orders(db_session)
    res = _query_data(
        db_session, "SELECT SUM(amount) AS total FROM orders", make_user("super_admin")
    )
    assert "error" not in res, res.get("error")
    assert res["rows"][0]["total"] == 300.0


def test_admin_can_query_any_department(db_session):
    seed_orders(db_session)
    res = _query_data(
        db_session, "SELECT COUNT(*) AS n FROM orders", make_user("admin")
    )
    assert "error" not in res, res.get("error")
    assert res["rows"][0]["n"] == 2


def test_employee_can_only_query_own_department(db_session):
    """员工：不带本部门条件 → 拒绝；带本部门条件 → 放行"""
    seed_orders(db_session)
    employee = make_user("employee", "销售一部")

    blocked = _query_data(db_session, "SELECT COUNT(*) AS n FROM orders", employee)
    assert "error" in blocked and "权限不足" in blocked["error"]

    allowed = _query_data(
        db_session,
        "SELECT COUNT(*) AS n FROM orders WHERE department='销售一部'",
        employee,
    )
    assert "error" not in allowed, allowed.get("error")
    assert allowed["rows"][0]["n"] == 1


def test_employee_cannot_query_other_department(db_session):
    """员工想查别的部门 → 拒绝"""
    seed_orders(db_session)
    employee = make_user("employee", "销售一部")
    res = _query_data(
        db_session,
        "SELECT COUNT(*) AS n FROM orders WHERE department='市场部'",
        employee,
    )
    assert "error" in res and "权限不足" in res["error"]


def test_query_data_cannot_read_users_table(db_session):
    """数据工具即使收到 SELECT，也不能越出 orders 业务表范围。"""
    seed_orders(db_session)
    res = _query_data(
        db_session,
        "SELECT employee_no, hashed_password FROM users WHERE department='销售一部'",
        make_user("employee", "销售一部"),
    )
    assert "error" in res
    assert "业务表" in res["error"]


def test_query_data_rejects_subquery_outside_orders(db_session):
    """禁止通过 orders 外壳嵌套读取其他表。"""
    seed_orders(db_session)
    res = _query_data(
        db_session,
        "SELECT (SELECT COUNT(*) FROM users) AS n FROM orders WHERE department='销售一部'",
        make_user("employee", "销售一部"),
    )
    assert "error" in res
    assert "业务表" in res["error"]
