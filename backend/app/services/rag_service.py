"""RAG 回答服务：把「检索 + LLM 生成」组合成完整问答（Day 6 核心）"""

from app.ai.llm import llm_service
from app.services.retrieval_service import retrieval_service

# 角色 + 规则（防幻觉的主力写在这）
# Day 24.5 第 4 条：来源要"只列引用的"。之前模型把检索到的来源全罗列，
# 无关文档（如讲"流程"的教程 PDF）会混进"报销流程"的答案来源里——召回≠引用。
SYSTEM_PROMPT = (
    "你是一个企业知识助手。请根据下面提供的资料回答用户的问题。\n"
    "规则：\n"
    "1. 只依据资料回答，资料中没有的信息，明确说\"资料中没有相关内容\"。\n"
    "2. 回答要简洁、准确，用中文。\n"
    "3. 不要编造，不要使用资料之外的信息。\n"
    "4. 回答末尾如需列出来源文件，只列出你回答中实际引用的来源，不要罗列所有资料。\n"
    # Day 24.6：不同文档说法不一致时的行为。模型的默认倾向是"悄悄选一个"甚至
    # "糅合成一个答案"（这是幻觉的一种），必须显式要求它承认分歧、并列各方说法。
    "5. 当不同来源的资料说法不一致时，不要自行选择其中一个，也不要糅合成一个答案。"
    "明确告诉用户\"不同资料说法不一致\"，分别列出各来源的说法并注明出处，"
    "让用户自己核对判断。"
    "6. 遇到财务金额时，必须保留原文单位；原文是万元就写万元，不要自行改写成元，"
    "除非用户明确要求换算。\n"
    "7. 如果同一科目在不同章节同时出现概览表和附注明细表，优先以附注/明细表的原始金额作答，"
    "概览表只能作为辅助参考，并要说明单位不同或存在四舍五入。"
)

# Day 24.5：召回噪音过滤的"相关性倍数"。
# 背景：向量检索按语义相似度捞，语义词撞车（如"流程"）会把无关文档带进 top_k，
# 它的文件名就混进 sources，用户看到"来源文件里有个不相关的 PDF"。
# 过滤策略：距离越小越相似（Chroma 默认 L2），超过"最近距离 × 该倍数"的片段视为
# 明显不相关，直接丢弃——不进来，context 更纯、答案更准、来源更干净。
# 为什么用相对倍数而不是绝对阈值：L2 距离没有固定范围，绝对阈值没法预设；
# 相对倍数自适应（最相关的越近，过滤越严；整体都远就都保留），且测试可 mock。
_RELEVANCE_FACTOR = 2.0


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
        # 1. 检索：拿 Top K 片段（带来源文件名 + 距离）
        chunks = self.retrieval.search(question, k=k)

        # 没有资料就别硬答（防止 LLM 面对空资料瞎编）
        if not chunks:
            return {
                "answer": "知识库中还没有相关文档，请先上传文档。",
                "sources": [],
            }

        # Day 24.5：过滤明显不相关的召回（语义撞词"流程"把教程 PDF 带进来）。
        # 只在 RAG 的"决策层"做——retrieval 是通用检索，这里才决定"什么值得用"。
        chunks = self._filter_relevant(chunks)

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

    @staticmethod
    def _filter_relevant(chunks: list[dict]) -> list[dict]:
        """丢弃"明显不相关"的召回片段，保底至少留 1 个（Day 24.5）

        超过"最近距离 × _RELEVANCE_FACTOR"的视为噪音丢弃；全被丢弃时保底留第 1 个，
        避免"过滤后空 context"让回答退化成"知识库中没有相关内容"。

        Day 25：锚点从 chunks[0] 改为"所有片段的最小距离"——因为 hybrid 重排后
        顺序不再按距离升序（BM25 会把精确词条 chunk 拉高），chunks[0] 未必是最近。
        锚定真正最近的，才不会把"BM25 上浮的、向量距离略大的正确 chunk"误杀。
        """
        if not chunks:
            return chunks
        threshold = min(c["distance"] for c in chunks) * _RELEVANCE_FACTOR
        kept = [c for c in chunks if c["distance"] <= threshold]
        return kept or chunks[:1]


# 模块级单例
rag_service = RagService()
