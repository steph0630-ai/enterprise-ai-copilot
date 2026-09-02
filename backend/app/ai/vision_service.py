"""看图说话服务：把文档里的图片交给多模态模型，生成一段文字描述（Day 21）

用途：混图文档（流程图/架构图/系统截图）解析时图片被丢弃，图的语义进不了向量库。
这里用多模态模型把图"翻译"成文字，文字再走正常的 切分 → embedding → 入库 流程，
下游完全透明。

Day 21 换平台（2026-08-19）：视觉模型从硅基流动换到【智谱 BigModel】——
硅基流动账号已无可用视觉模型（72B/GLM-4V 全 403 Model disabled、7B/Omni 下架），
唯一能跑的 DeepSeek-OCR 只能抠字、理解不了流程图/图表语义，用户拍板换智谱
glm-4v-flash（免费）。两者都是 OpenAI 兼容 + base64 data URI，所以：
  - 和 llm.py 的关系从"同一个 key"变成"独立账号"：视觉走 VISION_API_KEY / VISION_BASE_URL
    （智谱的），对话走 LLM_API_KEY / LLM_BASE_URL（硅基流动的），互不相干。
  - 消息格式完全一样——content 里除了 text，还允许一个 image_url 块（base64 data URL）。

设计取舍：图片理解是"增强层"不是"必要层"。调用失败由调用方（document_service
的 enrich_pages_with_images）兜住——单张图失败跳过，不拖垮整个文档入库。
"""

import base64

from openai import OpenAI

from app.core.config import settings


class VisionService:
    """给图片生成文字描述（调用智谱的多模态模型）"""

    def __init__(self) -> None:
        # 智谱独立账号：key、base_url 从 VISION_* 取（和对话的 LLM_API_KEY 无关）。
        # key 为空时 client 置 None——避免 OpenAI() 构造直接抛 Missing credentials，
        # 让整个应用崩在 import 阶段。没配 key = 图片理解降级（调用方跳过），不致命。
        self.client = (
            OpenAI(
                api_key=settings.VISION_API_KEY,
                base_url=settings.VISION_BASE_URL,
            )
            if settings.VISION_API_KEY
            else None
        )

    def describe_image(self, image_bytes: bytes, mime: str = "image/png") -> str:
        """把一张图翻译成文字描述

        参数：
            image_bytes: 图片的原始字节（PNG/JPEG 均可）
            mime: 图片的 MIME 类型，如 image/png、image/jpeg

        返回：
            模型生成的描述文字；模型没吐字时返回空串（由调用方判断是否拼进去）

        OpenAI 兼容的图片输入格式：
            content 是列表，每个元素一个"块"——text 块放提示词，
            image_url 块放 data URL（base64 图片）。模型按顺序读这些块。
        """
        if self.client is None:
            return ""  # 没配智谱 key：图片理解降级，调用方（enrich）会跳过拼接
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content = [
            # 提示词刻意强调"提取内容"而不是"评价美丑"——防模型写"这是一张美丽的图"
            # Day 23：从"图中文字原样列出"（流水账，检索价值低）改成"主题概括 + 关键条目"
            # （输出像检索摘要，主题词在前，向量检索才容易命中）。
            {
                "type": "text",
                "text": (
                    "你是企业知识库的图片理解器。请把这张图概括成一段【可检索的文字摘要】："
                    "1) 先一句话说清这张图在讲什么（主题/应用场景）；"
                    "2) 再列出关键条目、文字、结构（流程/架构/表格的结论和趋势）。"
                    "3) 若这是规格/参数/型号页，要区分「产品型号」与「认证/参考编号」"
                    "（如 RoHS、R36368 这类认证号），别把认证编号当成产品型号；"
                    "型号以图上明确标注的为准（如 T0016/T0016L）。"
                    "目标是让不看图的人靠这段文字也能答对图里的内容。"
                    "不要评价图片、不要客套，控制在 150 字以内。"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            },
        ]
        response = self.client.chat.completions.create(
            model=settings.VISION_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=settings.LLM_TEMPERATURE,  # 提取要准不要发挥
            max_tokens=300,
        )
        return response.choices[0].message.content or ""


# 模块级单例：整个应用共用一个客户端
vision_service = VisionService()
