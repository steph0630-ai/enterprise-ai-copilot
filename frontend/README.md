# Frontend

Enterprise AI Copilot 的 Vue 3 前端。

```powershell
npm ci
npm run dev
```

生产构建：

```powershell
npm run build
```

开发环境的 `/api` 请求由 Vite 代理到 `http://localhost:8000`；容器环境由 Nginx 转发到后端服务。
