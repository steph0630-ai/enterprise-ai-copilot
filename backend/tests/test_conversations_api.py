"""会话管理接口测试（Day 24：前端刷新不丢历史）

覆盖：会话列表（标题生成/截断、用户隔离、updated_at 排序）、详情（owner 全量
历史 / 非 owner 404 / 不存在 404）、删除（级联清 messages、当前会话消失）。

Mock 原则同 test_agent_api.py：把 agent_service.answer 打桩，走真实 /chat 接口
造数据——链路是真的，LLM 是假的，省 token、结果确定。
"""

import pytest

from app.models.conversation import Message
from app.services.conversation_service import conversation_service


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """所有会话测试共用：Agent 回答打桩，避免真调 LLM"""
    from app.api.v1 import agent as agent_api

    monkeypatch.setattr(
        agent_api.agent_service,
        "answer",
        lambda messages, db, user: {"answer": "（mock）收到。", "tools_used": []},
    )


def _ask(client, token, query, conv_id=""):
    """发一轮 Agent 问答（answer 已 mock），返回会话 id。

    conv_id 为空 = 新建会话；传入 = 在同一个会话里追加一轮（测多轮历史用）。
    """
    res = client.post(
        "/api/v1/agent/chat",
        json={"query": query, "conversation_id": conv_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()["conversation_id"]


def test_list_returns_conversation_with_title(client, user_factory, auth_token):
    """发一轮 → 列表出现该会话，title = 第一条问题原文"""
    user_factory("E100")
    token = auth_token("E100")
    conv_id = _ask(client, token, "报销流程是什么")

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    convs = res.json()
    assert [c["id"] for c in convs] == [conv_id]
    assert convs[0]["title"] == "报销流程是什么"  # 短问题原样做标题


def test_title_truncated_over_20_chars(client, user_factory, auth_token):
    """超长问题 → title 截前 20 字 + 省略号（省一次 LLM 调用的取舍）"""
    user_factory("E100")
    token = auth_token("E100")
    long_q = "请详细说明报销流程的各个环节以及审批权限的具体规定和所需材料"
    conv_id = _ask(client, token, long_q)

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    title = res.json()[0]["title"]
    assert title == long_q[:20] + "…"
    assert len(title) == 21


def test_list_isolation_between_users(client, user_factory, auth_token):
    """A、B 各建会话 → 各自列表只有自己的（用户隔离贯穿读接口）"""
    user_factory("E100", department="销售一部")
    user_factory("E200", department="销售二部")
    token_a = auth_token("E100")
    token_b = auth_token("E200")
    _ask(client, token_a, "A 的问题")
    _ask(client, token_b, "B 的问题")

    ids_a = [
        c["id"]
        for c in client.get(
            "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token_a}"}
        ).json()
    ]
    ids_b = [
        c["id"]
        for c in client.get(
            "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token_b}"}
        ).json()
    ]
    assert ids_a and ids_b
    assert set(ids_a) & set(ids_b) == set()  # 谁也看不见谁的


def test_detail_full_history(client, user_factory, auth_token):
    """详情：owner 拿到完整消息（旧→新），不是默认 10 条"""
    user_factory("E100")
    token = auth_token("E100")
    conv_id = _ask(client, token, "第一问")
    _ask(client, token, "第二问", conv_id)  # 同一会话追加第二轮 → 4 条消息

    res = client.get(
        f"/api/v1/agent/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == conv_id
    assert [m["role"] for m in data["messages"]] == ["user", "assistant", "user", "assistant"]
    assert data["messages"][0]["content"] == "第一问"


def test_detail_not_owned_404(client, user_factory, auth_token):
    """拿别人的会话 id 看详情 → 404（不泄露存在性）"""
    user_factory("E100")
    user_factory("E200")
    token_a = auth_token("E100")
    token_b = auth_token("E200")
    conv_id = _ask(client, token_a, "A 的问题")

    res = client.get(
        f"/api/v1/agent/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_detail_missing_404(client, user_factory, auth_token):
    """不存在的会话 id → 404"""
    user_factory("E100")
    token = auth_token("E100")
    res = client.get(
        "/api/v1/agent/conversations/no-such-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_delete_cascades_messages(client, user_factory, auth_token, db_session):
    """删除会话 → 列表消失、messages 表该会话记录清零（级联删）"""
    user_factory("E100")
    token = auth_token("E100")
    conv_id = _ask(client, token, "要删的问题")

    res = client.delete(
        f"/api/v1/agent/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    left = (
        db_session.query(Message)
        .filter(Message.conversation_id == conv_id)
        .count()
    )
    assert left == 0  # 级联：会话没了，消息也不剩

    convs = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert convs == []  # 当前用户会话列表空


def test_delete_others_404(client, user_factory, auth_token):
    """删别人的会话 → 404"""
    user_factory("E100")
    user_factory("E200")
    token_a = auth_token("E100")
    token_b = auth_token("E200")
    conv_id = _ask(client, token_a, "A 的问题")

    res = client.delete(
        f"/api/v1/agent/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_list_ordered_by_updated_at(db_session, user_factory, auth_token, client):
    """排序：后活动的会话排前面（老数据 updated_at=NULL 也不崩、排后面）

    不走 /chat 接口造（同秒时间戳排序不稳），直接在测试库建两个会话、
    显式控制 updated_at，再调列表接口看顺序。
    """
    from datetime import datetime

    from sqlalchemy import text

    from app.models.conversation import Conversation

    uid = user_factory("E100")
    token = auth_token("E100")
    db_session.add_all(
        [
            Conversation(
                id="conv-old",
                user_id=uid,
                title="旧会话",
                updated_at=datetime(2026, 8, 1),
            ),
            Conversation(
                id="conv-new",
                user_id=uid,
                title="新会话",
                updated_at=datetime(2026, 8, 20),
            ),
            # 老会话：Day 24 之前建的。注意显式 updated_at=None 没用——
            # 模型 server_default=func.now() 会让 ORM 省略该列、DB 填当前时间戳，
            # 所以 NULL 只能原生 SQL 造出来（也是真实迁移后数据的"万一"路径）
            Conversation(
                id="conv-null",
                user_id=uid,
                title=None,
                created_at=datetime(2026, 7, 1),
            ),
        ]
    )
    db_session.commit()
    db_session.execute(
        text("UPDATE conversations SET updated_at = NULL WHERE id = 'conv-null'")
    )
    db_session.commit()

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    ids = [c["id"] for c in res.json()]
    assert ids == ["conv-new", "conv-old", "conv-null"]  # COALESCE(updated_at, created_at) 倒序
    # title 为 NULL 原样返回，前端负责兜底显示"未命名对话"
    assert res.json()[-1]["title"] is None


def test_service_list_limit(db_session, user_factory):
    """list_by_user 默认最多 50 个（侧边栏不会一次拉爆）"""
    from app.models.conversation import Conversation

    uid = user_factory("E100")
    for i in range(3):
        db_session.add(Conversation(id=f"c{i}", user_id=uid, title=f"会话{i}"))
    db_session.commit()
    convs = conversation_service.list_by_user(uid, db_session, limit=2)
    assert len(convs) == 2


# ========== Day 24.5：老会话标题用"第一个问题"兜底（DeepSeek 风格） ==========

def test_list_null_title_falls_back_to_first_question(
    client, user_factory, auth_token, db_session
):
    """老会话 title 是 NULL → 列表显示第一条 user 消息（截断），不再显示"未命名对话" """
    from app.models.conversation import Conversation

    uid = user_factory("E100")
    token = auth_token("E100")
    db_session.add(
        Conversation(id="old-conv", user_id=uid, title=None)  # Day 24 之前的老会话
    )
    db_session.add(
        Message(conversation_id="old-conv", role="user", content="报销流程怎么走")
    )
    db_session.commit()

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    title = {c["id"]: c["title"] for c in res.json()}["old-conv"]
    assert title == "报销流程怎么走"  # 兜底成第一条问题，而不是 None


def test_list_fallback_title_truncated(client, user_factory, auth_token, db_session):
    """兜底标题超长 → 和 append 生成规则一致：截前 20 字 + 省略号"""
    from app.models.conversation import Conversation

    uid = user_factory("E100")
    token = auth_token("E100")
    long_q = "请详细说明报销流程的各个环节以及审批权限的具体规定和所需材料"
    db_session.add(Conversation(id="old-conv", user_id=uid, title=None))
    db_session.add(
        Message(conversation_id="old-conv", role="user", content=long_q)
    )
    db_session.commit()

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    title = {c["id"]: c["title"] for c in res.json()}["old-conv"]
    assert title == long_q[:20] + "…"


def test_list_empty_conversation_keeps_null(client, user_factory, auth_token, db_session):
    """空会话（一条消息都没有）→ title 仍为 None，前端兜底"未命名对话"（合理）"""
    from app.models.conversation import Conversation

    uid = user_factory("E100")
    token = auth_token("E100")
    db_session.add(Conversation(id="empty-conv", user_id=uid, title=None))
    db_session.commit()

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    title = {c["id"]: c["title"] for c in res.json()}["empty-conv"]
    assert title is None


def test_list_existing_title_not_duplicated(client, user_factory, auth_token, db_session):
    """新会话 title 已生成 → 列表返回存的值，不被兜底逻辑二次处理"""
    from app.models.conversation import Conversation

    uid = user_factory("E100")
    token = auth_token("E100")
    db_session.add(Conversation(id="new-conv", user_id=uid, title="报销流程"))
    db_session.add(
        Message(conversation_id="new-conv", role="user", content="报销流程是什么")
    )
    db_session.commit()

    res = client.get(
        "/api/v1/agent/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    title = {c["id"]: c["title"] for c in res.json()}["new-conv"]
    assert title == "报销流程"  # 用存的值，不变成"报销流程是什么"
