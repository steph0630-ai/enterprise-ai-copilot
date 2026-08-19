"""Agent 接口测试（Day 16）：登录是硬门槛，带 token 能问

Mock 原则：把 agent_service.answer 打桩——测试只验证"接口链路 + 会话落库"，
绝不真调 LLM（省 token、结果确定、跑得快）。
"""


def test_agent_chat_requires_auth(client):
    """不带 token 调 Agent → 401（Day 12 起 Agent 就要登录）"""
    res = client.post("/api/v1/agent/chat", json={"query": "报销流程是什么"})
    assert res.status_code == 401


def test_agent_chat_works_with_token(client, user_factory, auth_token, monkeypatch):
    from app.api.v1 import agent as agent_api

    # 打桩：不真调 LLM，固定返回
    monkeypatch.setattr(
        agent_api.agent_service,
        "answer",
        lambda messages, db, user: {"answer": "（mock）报销流程第一步是填表。", "tools_used": []},
    )

    user_factory("E100", role="employee", department="销售一部")
    token = auth_token("E100")
    res = client.post(
        "/api/v1/agent/chat",
        json={"query": "报销流程是什么"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["answer"] == "（mock）报销流程第一步是填表。"
    assert data["conversation_id"]  # 多轮记忆的会话已创建


def test_agent_chat_stores_history(client, user_factory, auth_token, monkeypatch, db_session):
    """Agent 答完，这一轮问答落库（Day 11 多轮记忆）"""
    from app.api.v1 import agent as agent_api
    from app.models.conversation import Message

    monkeypatch.setattr(
        agent_api.agent_service,
        "answer",
        lambda messages, db, user: {"answer": "测试答案", "tools_used": []},
    )

    user_factory("E100", role="employee")
    token = auth_token("E100")
    res = client.post(
        "/api/v1/agent/chat",
        json={"query": "你好"},
        headers={"Authorization": f"Bearer {token}"},
    )
    conv_id = res.json()["conversation_id"]

    # 库里应该有 2 条消息：user + assistant
    msgs = (
        db_session.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.id)
        .all()
    )
    assert [m.role for m in msgs] == ["user", "assistant"]
