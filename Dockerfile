# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ===== Stage 2: Runtime =====
FROM python:3.11-slim

# 安装运行时依赖 (lxml 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 pip 包
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# 复制项目代码
COPY trend_radar/ ./trend_radar/
COPY scripts/ ./scripts/
COPY config.yaml .
COPY .env .

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 8088

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8088/api/health', timeout=3)" || exit 1

CMD ["python", "-m", "trend_radar.web.app"]