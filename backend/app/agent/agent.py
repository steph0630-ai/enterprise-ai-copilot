"""Agent 服务：工具调用循环（Day 7 核心）

循环逻辑：
  1. 把问题发给模型（带上工具说明书 TOOLS）
  2. 模型二选一：
     - 给纯文字答案（说明不需要工具）→ 返回
     - 给出 tool_calls（说明要调工具）→ 执行工具，结果回传，再问一次
  3. 重复直到模型给纯文字答案（或达到最大轮数）

要点：assistant 那条带 tool_calls 的消息要原样加回历史，
每个工具结果要按 role="tool" + tool_call_id 回传，模型才对得上号。
"""

import json

from sqlalchemy.orm import Session

from app.agent.tools import TOOLS, run_tool
from app.ai.llm import llm_service


class AgentService:
    """把 LLM + 工具组合成"会判断、会动手"的 Agent"""

    def __init__(self) -> None:
        self.llm = llm_service  # 复用单例，不重复建客户端

    def answer(self, question: str, db: Session, max_rounds: int = 4) -> dict:
        """回答一个问题，返回 {answer, tools_used}"""
        # 1. 初始消息：只有用户问题
        messages = [{"role": "user", "content": question}]
        tools_used: list[str] = []

        for _ in range(max_rounds):
            # 2. 问模型（带上工具说明书，让它"看见"有哪些工具可用）
            msg = self.llm.complete(messages, tools=TOOLS)

            # 3. 模型没要工具 → 这就是最终答案
            if not msg.tool_calls:
                return {"answer": msg.content or "", "tools_used": tools_used}

            # 4. 模型要了工具 → 把这条 assistant 消息原样加回历史
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [c.model_dump() for c in msg.tool_calls],
                }
            )

            # 5. 逐个执行工具，结果以 role="tool" 回传
            for call in msg.tool_calls:
                name = call.function.name
                try:
                    # arguments 是 JSON 字符串，要解析成 dict
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                tools_used.append(name)
                result = run_tool(name, args, db)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            # 回到循环顶，再问一次模型（现在它手里有工具结果了）

        return {"answer": "已达最大轮次仍未给出答案", "tools_used": tools_used}


# 模块级单例
agent_service = AgentService()
