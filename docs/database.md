# 数据库设计

四种数据各住最合适的"房子"：结构化业务数据 → MySQL，知识文档 → PostgreSQL（pgvector）。

## ① MySQL：业务数据

### users（用户）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INT | 主键 |
| username | VARCHAR | 登录名 |
| password_hash | VARCHAR | 加密后的密码（不存明文） |
| role | VARCHAR | `employee` 普通员工 / `admin` 管理员 |
| department | VARCHAR | 部门（权限过滤用） |
| created_at | DATETIME | 创建时间 |

### products（产品）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INT | 主键 |
| name | VARCHAR | 产品名 |
| price | DECIMAL | 价格（用 DECIMAL，避免浮点误差） |

### orders（订单）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INT | 主键 |
| user_id | INT | 外键 → users.id（谁买的） |
| product_id | INT | 外键 → products.id（买了什么） |
| amount | DECIMAL | 金额 |
| created_at | DATETIME | 下单时间 |

## ② PostgreSQL（pgvector）：知识文档

### documents

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INT | 主键 |
| title | VARCHAR | 文档标题 |
| content | TEXT | 文档原文 |
| embedding | vector | 文本向量（RAG 检索用） |
| uploaded_by | INT | 上传者 |
| created_at | DATETIME | 上传时间 |

## 设计原则

- **外键**：orders 用 `user_id` / `product_id` 关联，而不是重复抄名字 → 只存一遍、改一次全生效。
- **密码加盐哈希**：绝不明文存储，防泄露。
- **类型决定房子**：`embedding` 是向量类型，只有 pgvector 支持，所以文档单独住 PostgreSQL。
- **统计口径**：数订单用 `COUNT(*)`，加金额用 `SUM(amount)`。
