import logging

from fastapi import FastAPI

from app.api.v1 import users, documents, knowledge, chat, agent, conversations

# Day 23：项目原本没有任何日志配置，标准库 logger 默认只显示 WARNING。
# 图片增强层的"丢图可感知"日志是 INFO 级（入库结束的总结），不配 basicConfig 就看不见。
# 放这里：uvicorn 启动时 import main.py 即生效，后台入库线程也走同一进程。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Enterprise AI Copilot API",
    description="企业智能知识与数据分析 Agent 后端",
    version="0.1.0",
)

# 注册 v1 用户路由
app.include_router(users.router, prefix="/api/v1")
# 注册 v1 文档路由
app.include_router(documents.router, prefix="/api/v1")
# 注册 v1 知识检索路由
app.include_router(knowledge.router, prefix="/api/v1")
# 注册 v1 对话路由（Day 6：RAG 生成答案）
app.include_router(chat.router, prefix="/api/v1")
# 注册 v1 Agent 路由（Day 7：判断任务 + 调用工具）
app.include_router(agent.router, prefix="/api/v1")
# 注册 v1 会话管理路由（Day 24：列表 / 详情 / 删除）
app.include_router(conversations.router, prefix="/api/v1")


@app.get("/health")
def health():
    """健康检查：确认服务是否在运行"""
    return {"status": "ok"}
