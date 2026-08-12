# 基础镜像：官方 Python 3.13 精简版
FROM python:3.13-slim

# 工作目录
WORKDIR /app

# 先复制依赖清单再装（利用 Docker 缓存，改代码不用重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
