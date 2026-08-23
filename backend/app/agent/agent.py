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
import time

from sqlalchemy.orm import Session

from app.agent.tools import TOOLS, _force_retrieve, _is_meta_query, build_tools, run_tool
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
        forced = False  # Day 25.3：幻觉兜底只做一次，防死循环

        for _ in range(max_rounds):
            # 2. 问模型（带上工具说明书，让它"看见"有哪些工具可用）
            #    非管理员：build_tools 会把"只能查本部门"写进 query_data 描述
            msg = self.llm.complete(messages, tools=build_tools(user))

            # 3. 模型没要工具 → 本来这是最终答案，但先过"幻觉兜底"：
            #    模型没调任何工具就答，可能是"不检索就编"（还假称根据知识库）。
            #    提示词规则是软的，代码兜底才是硬的——不是元问题就强制检索
            #    注入 context 重问一次，这次它手里有资料，无从编造。
            if not msg.tool_calls:
                current_query = (
                    messages[-1]["content"]
                    if messages and messages[-1]["role"] == "user" else ""
                )
                if (not tools_used and not forced and current_query
                        and not _is_meta_query(current_query)):
                    forced = True
                    tools_used.append("search_knowledge")  # 前端亮徽章：确实用了知识库
                    # Day 25.3 措辞要点：历史里可能已有错误的旧答案（历史污染，
                    # 模型会延续历史数字）。必须明确"以资料为唯一依据，忽略历史冲突"，
                    # 否则资料注入也压不过历史里的 5,000,000。
                    messages.append({
                        "role": "system",
                        "content": (
                            "以下参考资料来自企业知识库，是当前问题的唯一权威依据。"
                            "如果它与本对话之前提到的任何数字或回答不一致，"
                            "一律以本资料为准，不得重复之前提到的数字。\n"
                            f"参考资料：\n{_force_retrieve(current_query)}"
                        ),
                    })
                    continue  # 重问一次
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
        forced = False  # Day 25.3：幻觉兜底只做一次，防死循环

        for _ in range(max_rounds):
            stream = self.llm.complete_stream(messages, tools=build_tools(user))

            text_parts: list[str] = []   # 本轮的文字（可能是模型先写的"草稿"，不立即吐）
            tool_calls: list[dict] = []  # 累计出来的工具调用
            finish_reason = None         # 最后一个 chunk 的结束原因（兜底用）

            for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason

                # 1. 模型吐了文字 → 先攒着，不立即转发（Day 25.4）。
                #    模型常"先写一段草稿再调工具"，若边到边吐，草稿会把前端答案
                #    和正式答案拼成两份。攒住，等这轮确认不调工具才吐。
                if delta.content:
                    text_parts.append(delta.content)

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

            # 4. 这一轮没要工具 → 先过"幻觉兜底"（同 answer），再吐答案收工。
            #    Day 25.4：现在才把攒的字吐出去——草稿轮（调了工具）的字被丢掉，
            #    只有这一轮"确实没调工具"的文字才到前端，答案只出现一次。
            if not tool_calls:
                current_query = (
                    messages[-1]["content"]
                    if messages and messages[-1]["role"] == "user" else ""
                )
                if (not tools_used and not forced and current_query
                        and not _is_meta_query(current_query)):
                    forced = True
                    tools_used.append("search_knowledge")
                    messages.append({
                        "role": "system",
                        "content": (
                            "以下参考资料来自企业知识库，是当前问题的唯一权威依据。"
                            "如果它与本对话之前提到的任何数字或回答不一致，"
                            "一律以本资料为准，不得重复之前提到的数字。\n"
                            f"参考资料：\n{_force_retrieve(current_query)}"
                        ),
                    })
                    continue  # 带着资料重新问（这轮的草稿不要了）
                if not text_parts:  # Day 18 防御：一个字没吐（上游偶发空流）→ 非流式兜底
                    fallback = self._fallback_answer(messages)
                    if fallback:
                        yielded_token = True
                        yield {"type": "token", "content": fallback}
                else:
                    yielded_token = True
                    # Day 25.4 修打字机：攒住的答案不能"一次全吐"（无流式感），
                    # 也不能边到边吐（会泄调工具前的草稿）。折中：确认是最终答案后，
                    # 切成小段、段间小停顿逐帧吐——前端逐段拼接=打字机效果，且不重复。
                    _TYPING_CHUNK = 6    # 每帧吐几个字（约 200 字/秒的打字节奏）
                    _TYPING_DELAY = 0.03
                    text = "".join(text_parts)
                    for i in range(0, len(text), _TYPING_CHUNK):
                        yield {"type": "token", "content": text[i:i + _TYPING_CHUNK]}
                        time.sleep(_TYPING_DELAY)
                yield {"type": "done", "tools_used": tools_used}
                return

            # 5. 这轮要工具 → 草稿文字只进历史（不给用户），把带 tool_calls 的话
            #    原样加回历史（缺了它模型对不上号），逐个执行工具，结果回传。
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
