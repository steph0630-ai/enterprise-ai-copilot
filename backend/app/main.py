from fastapi import FastAPI

from app.api.v1 import users, documents, knowledge, chat, agent

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


@app.get("/health")
def health():
    """健康检查：确认服务是否在运行"""
    return {"status": "ok"}
