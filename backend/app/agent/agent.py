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

from app.agent.tools import TOOLS, build_tools, run_tool
from app.ai.llm import llm_service


class AgentService:
    """把 LLM + 工具组合成"会判断、会动手"的 Agent"""

    def __init__(self) -> None:
        self.llm = llm_service  # 复用单例，不重复建客户端

    def answer(self, messages: list[dict], db: Session, user=None, max_rounds: int = 5) -> dict:
        """按给定消息列表走 Agent 循环，返回 {answer, tools_used}

        Day 11 重构：不再自己拼"只有一个问题"的消息，
        而是由接口层把"历史 + 当前问题"组装好传进来（多轮记忆）。
        Day 12 加 user：非管理员的工具说明书会带上部门限制，query_data 校验权限。
        注意：本方法会原地往 messages 里追加 assistant/tool 消息，调用方传入的是新列表即可。
        """
        # 1. messages 就是初始上下文（含历史），直接开循环
        tools_used: list[str] = []

        for _ in range(max_rounds):
            # 2. 问模型（带上工具说明书，让它"看见"有哪些工具可用）
            #    非管理员：build_tools 会把"只能查本部门"写进 query_data 描述
            msg = self.llm.complete(messages, tools=build_tools(user))

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
                result = run_tool(name, args, db, user)  # user 带去部门权限

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            # 回到循环顶，再问一次模型（现在它手里有工具结果了）

        return {"answer": "已达最大轮次仍未给出答案", "tools_used": tools_used}

    def answer_stream(self, messages: list[dict], db: Session, user=None, max_rounds: int = 5):
        """流式版 Agent：答案逐字往外吐（Day 10）

        Day 11 重构：和 answer() 一样收"含历史的完整消息列表"，
        多轮记忆由接口层组装，本方法专注"走循环、吐事件"。
        Day 12 加 user：部门权限（同 answer()）。

        yield 的事件（SSE 帧，前端按 type 分发）：
            {"type": "token", "content": "..."}   模型吐的一段文字
            {"type": "tool",  "name": "..."}      准备调用某工具（前端可亮徽章）
            {"type": "done",  "tools_used": [...]} 全部结束
        """
        tools_used: list[str] = []
        yielded_token = False  # Day 18：整个流里有没有吐过一个字（空响应兜底用）

        for _ in range(max_rounds):
            stream = self.llm.complete_stream(messages, tools=build_tools(user))

            text_parts: list[str] = []   # 本轮的纯文字（模型回答前可能先说一句"我来查"）
            tool_calls: list[dict] = []  # 累计出来的工具调用
            finish_reason = None         # 最后一个 chunk 的结束原因（兜底用）

            for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason

                # 1. 模型吐了文字 → 原样转给前端
                if delta.content:
                    text_parts.append(delta.content)
                    yielded_token = True
                    yield {"type": "token", "content": delta.content}

                # 2. 工具调用是"零散拼装"来的：同一个 index 是同一个调用，
                #    名字/参数可能分几个 chunk 到，arguments 要一段段拼起来。
                #    注意：流式 chunk 里没有 .message，工具调用只能从 delta 取。
                for tc in delta.tool_calls or []:
                    index = tc.index
                    while len(tool_calls) <= index:
                        tool_calls.append(
                            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                        )
                    if tc.id:
                        tool_calls[index]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls[index]["function"]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls[index]["function"]["arguments"] += tc.function.arguments

            # 3. 安全网：个别平台不把 tool_calls 流式吐出来（delta 里没有），
            #    但会用 finish_reason="tool_calls" 提示"我要调工具"。
            #    这时改走非流式再问一次，把完整的 tool_calls 拿回来（只多花一次调用）。
            if not tool_calls and finish_reason == "tool_calls":
                msg = self.llm.complete(messages, tools=TOOLS)
                tool_calls = [c.model_dump() for c in msg.tool_calls or []]

            # 4. 这一轮没要工具 → 就是最终答案，收工
            if not tool_calls:
                # Day 18 防御：一个字没吐（上游偶发空流）→ 非流式兜底，别让前端看到空答案
                if not yielded_token:
                    fallback = self._fallback_answer(messages)
                    if fallback:
                        yield {"type": "token", "content": fallback}
                yield {"type": "done", "tools_used": tools_used}
                return

            # 5. 要工具 → 把模型这句"带 tool_calls"的话原样加回历史（缺了它模型对不上号），
            #    逐个执行工具，结果回传，回到循环顶再问一次
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(text_parts),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tools_used.append(name)
                yield {"type": "tool", "name": name}  # 让前端先亮起"正在调工具"的徽章
                result = run_tool(name, args, db, user)  # user 带去部门权限
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        # 达到最大轮次还没给答案，同样兜底一次
        if not yielded_token:
            fallback = self._fallback_answer(messages)
            if fallback:
                yield {"type": "token", "content": fallback}
        yield {"type": "done", "tools_used": tools_used}

    def _fallback_answer(self, messages: list[dict]) -> str:
        """空响应兜底（Day 18）：流式一个字都没吐时，非流式再问一次

        上游（硅基流动/DeepSeek）偶发会返回空流：finish_reason=stop 但 content 为空。
        这种时候别让用户看到"（Agent 没有返回内容）"，用最稳的非流式调用补救。
        不带 tools——我们只要一句正常回答，不再让它调工具。
        返回空字符串 = 兜底也失败，调用方保持原样。
        """
        try:
            msg = self.llm.complete(messages)
            return (msg.content or "").strip()
        except Exception:
            return ""


# 模块级单例
agent_service = AgentService()
