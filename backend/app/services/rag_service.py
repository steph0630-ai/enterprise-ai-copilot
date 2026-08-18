"""RAG 回答服务：把「检索 + LLM 生成」组合成完整问答（Day 6 核心）"""

from app.ai.llm import llm_service
from app.services.retrieval_service import retrieval_service

# 角色 + 规则（防幻觉的主力写在这）
SYSTEM_PROMPT = (
    "你是一个企业知识助手。请根据下面提供的资料回答用户的问题。\n"
    "规则：\n"
    "1. 只依据资料回答，资料中没有的信息，明确说\"资料中没有相关内容\"。\n"
    "2. 回答要简洁、准确，用中文。\n"
    "3. 不要编造，不要使用资料之外的信息。"
)


class RagService:
    """RAG 完整查询链路：问题 → 检索 Top K → 拼 Prompt → LLM 生成 → 答案+出处

    它自己不干具体活，而是组合两个底层能力：
    RetrievalService（找素材）+ LLMService（组织答案）。
    """

    def __init__(self) -> None:
        self.retrieval = retrieval_service
        self.llm = llm_service

    def answer(self, question: str, k: int = 3) -> dict:
        """问一个知识类问题，返回 {answer, sources}"""
        # 1. 检索：拿 Top K 片段（带来源文件名）
        chunks = self.retrieval.search(question, k=k)

        # 没有资料就别硬答（防止 LLM 面对空资料瞎编）
        if not chunks:
            return {
                "answer": "知识库中还没有相关文档，请先上传文档。",
                "sources": [],
            }

        # 2. 拼 Prompt 的 Context 段：把片段整理成"资料"段落
        context = "\n\n".join(
            f"[片段{i + 1} 来源:{chunk['source']}]\n{chunk['text']}"
            for i, chunk in enumerate(chunks)
        )

        # 3. 生成答案（System 规则 + 资料 + 问题 一起交给 LLM）
        answer = self.llm.chat(SYSTEM_PROMPT, context, question)

        # 4. 出处一起返回（可追溯）。用 set 去重，只留文件名单
        sources = list({chunk["source"] for chunk in chunks})
        return {"answer": answer, "sources": sources}


# 模块级单例
rag_service = RagService()
