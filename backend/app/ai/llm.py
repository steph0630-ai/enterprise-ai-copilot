"""LLM 对话服务：把「问题 + 资料」变成一段自然语言答案（调用硅基流动的对话模型）"""

from openai import OpenAI

from app.core.config import settings


class LLMService:
    """基于给定的资料，生成一段自然语言回答

    和 EmbeddingService 一样，底层走硅基流动的 OpenAI 兼容接口。
    它只负责"生成"，不负责"检索"——检索是 RetrievalService 的活，
    我们把它俩在 RagService 里组合起来。
    """

    def __init__(self) -> None:
        # 同一个账号、同一个 base_url，只是用途不同（换了个 key 变量名）
        self.client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )

    def chat(self, system_prompt: str, context: str, question: str) -> str:
        """给模型一份"作业单"（System + 资料 + 问题），拿到回答文字

        参数：
            system_prompt: 角色和规则（比如"只依据资料回答，没有就说不知道"）
            context: 检索到的资料片段（拼好了的文本）
            question: 用户的问题

        返回：
            模型生成的回答文字
        """
        messages = [
            # 第一段：System —— 角色 + 规则（防幻觉的主力在这）
            {"role": "system", "content": system_prompt},
            # 第二段：User —— 资料 + 问题，用【资料】标记包住，模型才分得清哪些是证据
            {
                "role": "user",
                "content": f"【资料】\n{context}\n\n【问题】\n{question}",
            },
        ]
        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,  # 调低，知识问答要准不要创意
        )
        return response.choices[0].message.content or ""


# 模块级单例：整个应用共用一个客户端
llm_service = LLMService()
