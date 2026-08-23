"""Agent 幻觉兜底测试（Day 25.3：模型不调工具就答的强制检索）

背景：模型"经常"违反规则 1 不调 search_knowledge 就直接答，还编数字假称
"根据企业知识库"。提示词管不住，代码兜底——answer 里模型没调任何工具就答
且非元问题时，强制检索注入 context 重问一次，tools_used 记 search_knowledge
让前端亮徽章。兜底只做一次防死循环。
"""

from types import SimpleNamespace

from app.agent.agent import agent_service
from app.agent.tools import _is_meta_query, rag_service


class _Msg:
    """假的 llm.complete 返回值（answer 只用 content / tool_calls）"""

    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


def _mock_llm(monkeypatch, sequence):
    """llm.complete 按 sequence 依次返回；记录调用次数"""
    calls = {"n": 0}

    def fake(messages, tools=None):
        i = calls["n"]
        calls["n"] += 1
        return sequence[min(i, len(sequence) - 1)]

    monkeypatch.setattr(agent_service.llm, "complete", fake)
    return calls


def _mock_retrieve(monkeypatch, chunks):
    """把知识库检索打桩（兜底 _force_retrieve 会走它）"""
    monkeypatch.setattr(
        rag_service.retrieval, "search",
        lambda q, k=3: chunks,
    )


def test_answer_forces_retrieve_when_no_tool_call(monkeypatch):
    """模型不调工具直接答 → 强制检索注入 → 重问返回基于资料的答案"""
    _mock_retrieve(monkeypatch, [
        {"text": "其他非流动资产 11,463.63", "source": "年报.pdf", "distance": 0.5},
    ])
    calls = _mock_llm(monkeypatch, [
        _Msg("根据知识库，余额是 5,000,000", []),   # 第一次：幻觉，不调工具
        _Msg("其他非流动资产期末余额为 11,463.63", []),  # 第二次：基于注入资料
    ])
    messages = [
        {"role": "system", "content": "你是企业助手"},
        {"role": "user", "content": "其他非流动资产期末余额合计是多少"},
    ]

    res = agent_service.answer(messages, db=None)

    assert calls["n"] == 2                      # 兜底重问了一次
    assert "5,000,000" not in res["answer"]     # 幻觉答案被丢弃
    assert "11,463.63" in res["answer"]         # 用了注入资料后的回答
    assert res["tools_used"] == ["search_knowledge"]  # 前端能亮徽章
    assert any("参考资料" in m["content"] for m in messages)  # 确实注入过


def test_answer_forcing_only_once(monkeypatch):
    """兜底只做一次：注入资料后模型仍不调工具 → 直接返回第二次答案（不死循环）"""
    _mock_retrieve(monkeypatch, [
        {"text": "资料内容", "source": "年报.pdf", "distance": 0.5},
    ])
    calls = _mock_llm(monkeypatch, [
        _Msg("幻觉答案1", []),
        _Msg("幻觉答案2", []),  # 注入后仍乱答，但兜底只做一次 → 返回这个
    ])
    messages = [{"role": "user", "content": "报销流程是什么"}]

    res = agent_service.answer(messages, db=None)

    assert calls["n"] == 2
    assert res["answer"] == "幻觉答案2"
    assert res["tools_used"] == ["search_knowledge"]


def test_answer_no_forcing_for_meta_query(monkeypatch):
    """元问题（问系统本身）→ 不触发兜底，直接返回（规则 2 允许不检索）"""
    _mock_retrieve(monkeypatch, [])
    calls = _mock_llm(monkeypatch, [_Msg("我用 FastAPI 搭建", [])])
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你的技术栈是什么"},
    ]

    res = agent_service.answer(messages, db=None)

    assert calls["n"] == 1            # 没重问
    assert res["tools_used"] == []
    assert "FastAPI" in res["answer"]


def test_system_prompt_finance_unit_rule(monkeypatch):
    """Agent 提示词要求财务金额保留原文单位，附注明细优先于概览表"""
    from app.api.v1 import agent as agent_api

    # _build_messages 会走 get_or_create + history（需要真库），这里打桩让它只拼字符串
    monkeypatch.setattr(agent_api.conversation_service, "get_or_create", lambda *a, **k: None)
    monkeypatch.setattr(agent_api.conversation_service, "history", lambda *a, **k: [])

    system = agent_api._build_messages(
        SimpleNamespace(query="其他非流动资产期末余额合计多少", conversation_id=""),
        SimpleNamespace(id=1, name="张三", employee_no="E100", role="employee", department="销售一部"),
        db=None,
    )[0][0]["content"]

    assert "财务金额必须保留原文单位" in system
    assert "附注/明细表的原始金额" in system


def test_is_meta_query():
    """元问题判断：'技术栈/你这个系统' 命中；具体业务问题不命中"""
    assert _is_meta_query("你的技术栈是什么")
    assert _is_meta_query("你这个系统支持什么")
    assert not _is_meta_query("其他非流动资产期末余额合计是多少")
    assert not _is_meta_query("报销流程是什么")
