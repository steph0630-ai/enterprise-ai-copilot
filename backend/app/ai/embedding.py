"""Embedding 服务：把文本转换成向量（调用硅基流动的 BGE 中文模型）"""

from openai import OpenAI

from app.core.config import settings


class EmbeddingService:
    """文本 → 向量

    底层走硅基流动（SiliconFlow）的 OpenAI 兼容接口，模型是 BGE（中文 embedding）。
    为什么单独封装成服务：把"用哪个模型"这个细节圈起来，
    以后换模型（本地 BGE / 通义 / 智谱）只改这里，业务代码一行不动。
    """

    def __init__(self) -> None:
        # 硅基流动的接口和 OpenAI 完全一样，只是 base_url 和 key 不同
        self.client = OpenAI(
            api_key=settings.EMBEDDING_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一批文本变成一批向量（入库时批量用）

        参数：
            texts: 文本列表，如 ["报销流程", "请假制度"]

        返回：
            向量列表，如 [[0.12, 0.33, ...], [0.21, 0.54, ...]]
        """
        if not texts:  # 空列表直接返回空，避免白调一次 API
            return []

        # input 一次可传多段文本，省请求次数（比逐条调用快、也省钱）
        response = self.client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )

        # response.data 按输入顺序返回，取每个的 embedding（一维向量）
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        """把单个问题变成单个向量（检索时用）"""
        return self.embed_documents([text])[0]


# 模块级单例：整个应用共用一个客户端（别每次请求都 new 一个 OpenAI 客户端）
embedding_service = EmbeddingService()
