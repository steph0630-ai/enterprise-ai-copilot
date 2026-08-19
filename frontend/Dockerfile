# 前端镜像（Day 17）：两阶段构建
# 阶段1：node 环境里把 Vue 编译成静态文件（dist/）
# 阶段2：只把静态文件丢给 nginx，镜像里没有 node、没有源码——又小又快又安全

# ===== 阶段 1：构建 =====
FROM node:20-alpine AS build
WORKDIR /app
# 先复制依赖清单再装（有 package-lock，用 npm ci 保证版本一致）
COPY package.json package-lock.json ./
RUN npm ci
# 再复制源码并构建
COPY . .
RUN npm run build

# ===== 阶段 2：托管 =====
FROM nginx:alpine
# 把构建产物拷进 nginx 的站点根目录
COPY --from=build /app/dist /usr/share/nginx/html
# 自定义配置：静态文件 + /api 反代（含 SSE 关缓冲）
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
