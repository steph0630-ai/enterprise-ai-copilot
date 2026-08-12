# 开发日志

## Day 2（2026-08-12）：FastAPI 后端骨架 + 用户系统

### 今天完成

1. ✅ FastAPI 工程结构（分层：api / services / models / database / core）
2. ✅ MySQL 连接（pymysql 驱动 + SQLAlchemy）
3. ✅ SQLAlchemy ORM 建表（`users` 表）
4. ✅ JWT 认证（注册 / 登录 / 当前用户）
5. ✅ Docker 环境（docker-compose 一键启动 mysql + fastapi）

### 关键理解

- **企业后端需要分层设计**：api（Controller）收请求、services（Service）管业务、models/database（DAO）访问数据。降低耦合、职责清晰、好维护好测试。
- **JWT 无状态认证**：前后端分离、多实例下不用共享 session，token 自带身份、秘钥验签防伪造。
- **密码用 bcrypt 加盐哈希**存，绝不存明文、不用可逆加密。

### 踩过的坑（面试素材）

| 坑 | 解决 |
| --- | --- |
| 端口 3306 被本机 MySQL 占用 | 容器映射 3307 |
| MySQL8 连接报 cryptography 缺失 | pip install cryptography |
| Swagger 无法授权（OAuth2PasswordBearer） | 改 HTTPBearer 直接贴 token |

### 下一步（Day 3）

企业知识库 RAG Pipeline：文件上传 → 文档解析 → Embedding → Vector DB → 检索接口。
