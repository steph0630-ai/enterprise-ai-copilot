# Enterprise AI Copilot

企业内部的知识问答 + 数据分析 Agent。员工用自然语言查企业文档和业务数据；部门管理员维护本部门知识库；超级管理员管理全局权限。

技术栈：Vue 3 + Vite 前端，FastAPI + SQLAlchemy 后端，DeepSeek 做对话、BGE 做向量、GLM-4V 读图，数据用 MySQL + Chroma，Docker Compose 一键起。

## 它能做什么

- 上传 PDF / DOCX / TXT / MD 文档，自动解析入库
- 文本、表格、文档里的图片都能解析（图片用视觉模型描述后入库）
- Embedding + Chroma 做语义检索，基于来源片段回答
- 直接问"订单总额"这类问题，Agent 会自己写 SQL 查数据库
- JWT 登录、员工 / 部门管理员 / 超级管理员三级权限、会话隔离
- 多知识库 ACL：私有、部门可见、全员可见和显式成员授权
- 文档后台处理、状态展示、失败原因记录

## 跑起来之前，先准备这些

1. **Docker**——compose 要它。
2. **模型 API Key**，都从 <https://api.siliconflow.cn> 注册拿（同一个 key）：
   - `LLM_API_KEY`——对话、Agent 用
   - `EMBEDDING_API_KEY`——文档向量化用

3. 另外 `VISION_API_KEY` 是**可选**的（智谱 <https://open.bigmodel.cn>），只影响文档里的图片解析——不填也能跑，只是图里的内容读不出来。

> `LLM_API_KEY` 和 `EMBEDDING_API_KEY` 必填，缺失时后端无法初始化 AI 客户端；`VISION_API_KEY` 可留空，只会关闭图片理解能力。

## 怎么跑

```powershell
# 1. 建后端环境变量文件
Copy-Item backend/.env.example backend/.env

# 2. 编辑 backend/.env，把上面的 key 填进去

# 3. 起服务
docker compose up --build

# 4. 打开
http://localhost:8080
```

首次启动时后端脚本会自动建表、刷演示账号和一个全员可见的默认知识库：`E001 / admin123`（超级管理员）、`E002 / 123456`、`E003 / 123456`（员工）。

## 数据从哪来

系统起来后是**空的**，得自己喂：

- **知识文档**：直接在前端页面上传 PDF / DOCX / TXT / MD 就行。
- **订单数据**（数据分析用）：`orders` 表要灌数据，脚本在 `backend/scripts/` 下：
  ```powershell
  cd backend
  .\venv\Scripts\python.exe scripts/import_orders.py 你的订单.csv  # 导入真实订单 CSV
  # 或
  .\venv\Scripts\python.exe scripts/import_olist.py               # 用 Olist 公开数据集
  ```

不灌这两样：问知识库是"没有相关内容"，问订单是"没有数据"。

## 本地开发（不走 Docker）

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

## 项目结构

```
backend/app/
  agent/          Agent 循环与工具（search_knowledge / query_data）
  ai/             LLM、Embedding、视觉模型客户端
  api/            FastAPI 路由与依赖
  models/         SQLAlchemy 模型
  services/       文档、检索、RAG、用户与会话
  vectorstore/    Chroma 封装
frontend/         Vue 前端
docs/             架构与核心流程说明
```

## 几点说明

- 国内网络 `docker compose up --build` 时，Dockerfile 已经带了**阿里云 PyPI 源**，build 依赖不会卡在国外 PyPI 上。
- 数据查询（query_data）默认只允许查配置的几张表（`NL2SQL_ALLOWED_TABLES`），敏感表不会给模型查。
- 这是**单机演示架构**。持久化任务队列、对象存储、知识库 ACL、生产安全加固这些还没做，在后续路线里。

## 文档

- [系统架构](docs/architecture.md)
- [数据库设计](docs/database.md)
- [Agent 流程](docs/agent-flow.md)
- [RAG Pipeline](docs/rag_pipeline.md)
- [项目定位](docs/project_design.md)
