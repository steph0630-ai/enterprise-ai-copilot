"""RAG 来源噪音过滤测试（Day 24.5）

背景：向量检索按语义相似度捞，语义词撞车（如"流程"）会把无关文档带进 top_k，
它的文件名就混进 sources，用户看到"来源文件里有个不相关的 PDF"。
修法：rag 检索后按距离丢弃明显不相关的片段 + 提示词要求只列引用来源。

覆盖：距离过滤（丢弃/保底/空）、SYSTEM_PROMPT 来源约束、Agent system prompt 来源约束。
原则：全打桩，不碰真实向量库/LLM。
"""

from types import SimpleNamespace

from app.services.rag_service import SYSTEM_PROMPT, rag_service


# ========== 距离过滤 ==========

def test_filter_drops_distant_chunk(monkeypatch):
    """明显不相关的召回（距离 3 倍于最近）被丢弃：不进 context、不进 sources"""
    captured = {}
    monkeypatch.setattr(
        rag_service.retrieval, "search",
        lambda q, k=3: [
            {"text": "报销单需填写并粘贴发票", "source": "报销制度.docx", "distance": 1.0},
            {"text": "财务复核后付款", "source": "company_policy.pdf", "distance": 1.5},
            {"text": "调用流程分四步", "source": "尚硅谷-05-Tools.pdf", "distance": 3.0},
        ],
    )

    def fake_chat(system, context, question):
        captured["context"] = context
        return "答案"

    monkeypatch.setattr(rag_service.llm, "chat", fake_chat)

    res = rag_service.answer("报销流程是什么", k=3)

    assert "尚硅谷" not in captured["context"], "无关 chunk 不应进 LLM context"
    assert "报销单需填写" in captured["context"], "相关 chunk 应保留"
    # sources 是 set 去重后的列表，迭代顺序随进程 hash seed 变——断言集合而不是列表
    assert set(res["sources"]) == {"报销制度.docx", "company_policy.pdf"}
    assert "尚硅谷" not in str(res["sources"])


def test_filter_keeps_related_enum_chunks(monkeypatch):
    """列举类问题召回的都是相关的（距离接近）→ 全部保留，不被误伤"""
    captured = {}
    monkeypatch.setattr(
        rag_service.retrieval, "search",
        lambda q, k=3: [
            {"text": "工具一", "source": "a.pdf", "distance": 0.8},
            {"text": "工具二", "source": "a.pdf", "distance": 0.9},
            {"text": "工具三", "source": "b.pdf", "distance": 1.4},
        ],
    )

    def fake_chat(system, context, question):
        captured["context"] = context
        return "答案"

    monkeypatch.setattr(rag_service.llm, "chat", fake_chat)

    res = rag_service.answer("有哪些工具", k=3)
    assert "工具三" in captured["context"]  # 1.4 < 0.8*2，算相关，保留（列举要全）
    assert len(res["sources"]) == 2


def test_filter_keeps_at_least_one(monkeypatch):
    """全部超阈值（极端）→ 保底留最近的第 1 个，不退回"知识库中没有相关内容" """
    captured = {}
    monkeypatch.setattr(
        rag_service.retrieval, "search",
        lambda q, k=3: [
            {"text": "最相关的片段", "source": "a.pdf", "distance": 1.0},
            {"text": "极不相关", "source": "b.pdf", "distance": 9.0},
        ],
    )

    def fake_chat(system, context, question):
        captured["context"] = context
        return "答案"

    monkeypatch.setattr(rag_service.llm, "chat", fake_chat)

    res = rag_service.answer("某问题", k=3)
    assert "最相关的片段" in captured["context"]
    assert res["sources"] == ["a.pdf"]


def test_filter_empty_chunks(monkeypatch):
    """检索为空 → 不硬答（走原有分支）"""
    monkeypatch.setattr(rag_service.retrieval, "search", lambda q, k=3: [])
    res = rag_service.answer("没有资料的问", k=3)
    assert "没有相关文档" in res["answer"]
    assert res["sources"] == []


# ========== 提示词约束 ==========

def test_system_prompt_source_constraint():
    """RAG 提示词要求"只列引用的来源"，防回退成罗列所有资料"""
    assert "只列出你回答中实际引用的来源" in SYSTEM_PROMPT
    assert "不要罗列所有资料" in SYSTEM_PROMPT


def test_agent_prompt_source_rule(monkeypatch):
    """Agent 的 system prompt 也有来源约束（Agent 链路走的是 agent.py 拼的 system）"""
    from app.api.v1 import agent as agent_api

    monkeypatch.setattr(
        agent_api.conversation_service, "get_or_create",
        lambda *a, **k: SimpleNamespace(id="c1"),
    )
    monkeypatch.setattr(
        agent_api.conversation_service, "history", lambda *a, **k: []
    )

    req = SimpleNamespace(query="报销流程是什么", conversation_id="")
    user = SimpleNamespace(
        id=1, name="张三", employee_no="E100", role="employee", department="销售一部"
    )
    messages, _ = agent_api._build_messages(req, user, db=None)
    system = messages[0]["content"]
    assert "只列出你实际引用的来源" in system
    assert "不要罗列工具返回的所有来源" in system


# ========== Day 24.6：冲突文档处理 ==========

def test_system_prompt_conflict_rule():
    """RAG 提示词要求：来源说法不一致时并列各方说法，不自行选择/糅合"""
    assert "说法不一致" in SYSTEM_PROMPT
    assert "不要自行选择其中一个" in SYSTEM_PROMPT
    assert "分别列出各来源的说法" in SYSTEM_PROMPT


def test_system_prompt_finance_unit_rule():
    """RAG 提示词要求保留财务金额原文单位，且附注明细优先于概览表"""
    assert "保留原文单位" in SYSTEM_PROMPT
    assert "原文是万元就写万元" in SYSTEM_PROMPT
    assert "附注/明细表" in SYSTEM_PROMPT


def test_agent_prompt_conflict_rule(monkeypatch):
    """Agent 的 system prompt 也有冲突规则（两条链路都要约束，防模型悄悄二选一）"""
    from app.api.v1 import agent as agent_api

    monkeypatch.setattr(
        agent_api.conversation_service, "get_or_create",
        lambda *a, **k: SimpleNamespace(id="c1"),
    )
    monkeypatch.setattr(
        agent_api.conversation_service, "history", lambda *a, **k: []
    )

    req = SimpleNamespace(query="报销流程是什么", conversation_id="")
    user = SimpleNamespace(
        id=1, name="张三", employee_no="E100", role="employee", department="销售一部"
    )
    messages, _ = agent_api._build_messages(req, user, db=None)
    system = messages[0]["content"]
    assert "说法不一致" in system
    assert "不要自行选择其中一个" in system
    assert "分别列出各来源的说法" in system
