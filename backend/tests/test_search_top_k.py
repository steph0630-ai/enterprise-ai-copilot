"""search_knowledge 的 top_k 自适应测试（Day 22）

背景：固定 top_k=3 导致两个真实故障——
  1. 列举/概括型问题召回不全（问工具列表只答 3/17 个）
  2. 宽泛问题下图描述 chunk（只占文本流 3.5%）被挤出前 3

改造：模型没传 top_k 时，后端按问题关键词推断（列举/概括→10，事实→8），
并 clamp 1~10（Agent 链路是唯一没夹紧 top_k 的地方，模型可能传 100000）。

Day 25.x 追加：具体事实类从 3 提到 8。实测单文档基准发现事实类答案片段
常排 top-3 之外（第 4~6 位），默认 3 会把答案漏出模型上下文。
"""

import app.agent.tools as tools


# ========== _infer_top_k：按问题类型推断 ==========

def test_infer_top_k_enumeration():
    """列举/概括类问题（有哪些/列出/总结）→ 10，召回要够全"""
    for q in [
        "这个教程讲了哪几个工具",
        "知识库里有哪几种制度",
        "列出所有流程",
        "帮我总结一下这份制度",
        "全部工具分别是什么",
    ]:
        assert tools._infer_top_k(q) == 10, q


def test_infer_top_k_factual():
    """单点事实类（数值/日期/人名）→ 8：答案片段常排 top-3 之外，默认 3 会漏（Day 25.x）"""
    for q in ["报销限额是多少", "报销流程是什么", "请假需要几天审批"]:
        assert tools._infer_top_k(q) == 8, q


# ========== _search_knowledge：k 怎么落到 RAG 层 ==========

def make_fake_answer(captured):
    """造一个 fake rag_service.answer：记录 k，返回固定结果"""
    def fake(query, k=3):
        captured["k"] = k
        return {"answer": f"answer for {query}", "sources": ["a.pdf"]}
    return fake


def test_search_knowledge_no_top_k_infers(monkeypatch):
    """模型没传 top_k → 按问题类型推断（列举→10）"""
    captured = {}
    monkeypatch.setattr(tools.rag_service, "answer", make_fake_answer(captured))
    tools._search_knowledge("这个教程讲了哪几个工具")
    assert captured["k"] == 10


def test_search_knowledge_no_top_k_infers_factual(monkeypatch):
    """模型没传 top_k → 单点事实类推断为 8（Day 25.x：答案常排 top-3 之外）"""
    captured = {}
    monkeypatch.setattr(tools.rag_service, "answer", make_fake_answer(captured))
    tools._search_knowledge("报销限额是多少")
    assert captured["k"] == 8


def test_search_knowledge_model_top_k_passthrough(monkeypatch):
    """模型特意传了 top_k=5 → 尊重它，不推断"""
    captured = {}
    monkeypatch.setattr(tools.rag_service, "answer", make_fake_answer(captured))
    tools._search_knowledge("报销限额是多少", top_k=5)
    assert captured["k"] == 5


def test_search_knowledge_clamps_upper(monkeypatch):
    """模型传 100 → clamp 到 10（防打爆上下文）"""
    captured = {}
    monkeypatch.setattr(tools.rag_service, "answer", make_fake_answer(captured))
    tools._search_knowledge("报销限额是多少", top_k=100)
    assert captured["k"] == 10


def test_search_knowledge_clamps_lower(monkeypatch):
    """模型传 -5（非法）→ 按问题类型推断兜底（列举→10）"""
    captured = {}
    monkeypatch.setattr(tools.rag_service, "answer", make_fake_answer(captured))
    tools._search_knowledge("这个教程讲了哪几个工具", top_k=-5)
    assert captured["k"] == 10


# ========== 工具说明书文案：防止 top_k 引导回退 ==========

def test_build_tools_top_k_description_guidance():
    """说明书应教模型：列举/概括和具体事实类都给 8~10，且不许再教"用 3 即可"（Day 25.x）"""
    desc = (
        tools.build_tools()[0]["function"]["parameters"]["properties"]["top_k"]["description"]
    )
    assert "8~10" in desc
    assert "具体事实类" in desc
    assert "用 3 即可" not in desc  # 事实类答案常排 top-3 之外，别再把模型往 3 上带
