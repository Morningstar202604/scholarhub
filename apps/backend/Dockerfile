# ScholarHUB 后端单容器镜像（含前端静态托管，单端口）。
# 构建上下文必须是仓库根目录：
#   docker build -f apps/backend/Dockerfile -t scholarhub .
FROM python:3.13-slim AS frontend-build

# --- 前端构建层 ---
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS backend

WORKDIR /app
# 先拷依赖清单利用层缓存
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/backend/app ./app
COPY apps/backend/alembic ./alembic
COPY apps/backend/alembic.ini ./
COPY apps/backend/deploy_server.py ./
COPY --from=frontend-build /build/dist ./static

ENV SCHOLARHUB_STATIC_DIR=/app/static \
    SCHOLARHUB_STORAGE_PATH=/data/uploads \
    PORT=8080
VOLUME ["/data/uploads"]
EXPOSE 8080

# 生产必须显式注入：SCHOLARHUB_DATABASE_URL / SECRET_KEY / FERNET_KEY /
# ADMIN_PASSWORD / ALLOWED_HOSTS（PG 部署先跑 alembic upgrade head，见 DEPLOY.md）。
CMD ["uv", "run", "--no-sync", "python", "deploy_server.py"]
