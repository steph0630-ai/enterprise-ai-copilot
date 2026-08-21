# Enterprise AI Copilot

企业内部知识问答与业务数据分析 Agent。员工可以用自然语言检索企业文档、查询业务数据并保留多轮会话；管理员可以管理文档、用户和角色。

## 当前能力

- PDF、DOCX、TXT、Markdown 文档入库
- 文本、表格和文档内图片解析
- Embedding + Chroma 语义检索
- 基于来源片段的 RAG 回答
- Agent 工具调用与流式输出
- JWT 登录、角色权限和会话隔离
- 文档后台处理、状态展示和失败原因记录
- Docker Compose 本地一键启动

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Element Plus、Nginx |
| 后端 | FastAPI、SQLAlchemy、Alembic、PyJWT |
| AI | OpenAI-compatible API、BGE Embedding、DeepSeek、GLM-4V |
| 数据 | MySQL、Chroma、本地文件存储 |
| 交付 | Docker、Docker Compose、pytest |

> 当前是单机开发/演示架构。持久化任务队列、对象存储、知识库 ACL、可观测性和生产安全加固仍在后续路线中。

## 项目结构

```text
backend/
  app/
    agent/          Agent 循环与工具
    ai/             LLM、Embedding、视觉模型客户端
    api/            FastAPI 路由与依赖
    models/         SQLAlchemy 模型
    services/       文档、检索、RAG、用户与会话服务
    vectorstore/    Chroma 封装
  alembic/          数据库迁移
  tests/            后端测试
frontend/           Vue 前端与 Nginx 配置
docs/               架构和核心流程文档
docker-compose.yml  本地容器编排
```

## Docker 启动

1. 创建后端环境变量文件：

   ```powershell
   Copy-Item backend/.env.example backend/.env
   ```

2. 在 `backend/.env` 中填写模型 API Key，并修改开发密钥。

3. 启动全部服务：

   ```powershell
   docker compose up --build
   ```

4. 打开 <http://localhost:8080>。

`docker-compose.yml` 中的数据库端口和演示账号仅用于本地开发，不应直接用于生产环境。

## 本地开发

后端：

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
npm ci
npm run dev
```

## 验证

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build

cd ..
docker compose config --quiet
```

## 文档

- [系统架构](docs/architecture.md)
- [数据库设计](docs/database.md)
- [Agent 流程](docs/agent-flow.md)
- [RAG Pipeline](docs/rag_pipeline.md)
- [项目定位](docs/project_design.md)
