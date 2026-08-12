from fastapi import FastAPI

from app.api.v1 import users

app = FastAPI(
    title="Enterprise AI Copilot API",
    description="企业智能知识与数据分析 Agent 后端",
    version="0.1.0",
)

# 注册 v1 用户路由
app.include_router(users.router, prefix="/api/v1")


@app.get("/health")
def health():
    """健康检查：确认服务是否在运行"""
    return {"status": "ok"}
