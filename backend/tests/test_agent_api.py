"""Agent 接口测试（Day 16）：登录是硬门槛，带 token 能问

Mock 原则：把 agent_service.answer 打桩——测试只验证"接口链路 + 会话落库"，
绝不真调 LLM（省 token、结果确定、跑得快）。
"""


def test_agent_chat_requires_auth(client):
    """不带 token 调 Agent → 401（Day 12 起 Agent 就要登录）"""
    res = client.post("/api/v1/agent/chat", json={"query": "报销流程是什么"})
    assert res.status_code == 401


def test_answer_stream_fallback_on_empty_stream(monkeypatch):
    """流式一个 token 都没吐（上游偶发空响应）→ 用非流式兜底补一句（Day 18 防御）

    背景：真实遇到过一次——用户问"Tools讲师是谁"，模型流 finish=stop 但 content 为空，
    前端显示"（Agent 没有返回内容）"。修复：answer_stream 结束时如果没吐过任何 token，
    非流式再问一次兜底。
    """
    from app.agent.agent import agent_service

    class FakeMsg:
        content = "兜底回答"
        tool_calls = None

    # 1) 流式返回空流（一个 chunk 都没有，模拟上游抽风）
    monkeypatch.setattr(
        agent_service.llm, "complete_stream", lambda messages, tools=None: iter([])
    )
    # 2) 非流式兜底正常返回
    monkeypatch.setattr(
        agent_service.llm, "complete", lambda messages, tools=None: FakeMsg()
    )

    events = list(agent_service.answer_stream([{"role": "user", "content": "你好"}], db=None))
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert tokens == ["兜底回答"]  # 空流也能兜出内容
    assert events[-1]["type"] == "done"


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
