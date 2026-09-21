# ScholarHUB 上线部署指南

> 代码状态：backend 646 tests / coverage 83.49%，frontend 100 tests，ruff/mypy/tsc 全绿（commit 99fbeb5 之后新增单端口部署能力）。

## 架构总览（推荐方案）

| 组件 | 推荐服务 | 说明 |
|---|---|---|
| 前端 SPA | **Cloudflare Pages** | 或走"单端口模式"由后端直接托管（见方案 B） |
| 后端 FastAPI | **Railway / Render / Fly.io / VPS** | ⚠️ Cloudflare Workers **跑不了** Python SQLAlchemy+asyncpg，后端必须落在一个能跑 Python 的宿主上 |
| PostgreSQL | **Neon / Supabase**（免费档可用） | 必须 PG：RLS 第二层隔离只在 PG 生效 |
| 文件存储（PDF） | **Cloudflare R2**（S3 兼容） | `storage.py` 已支持 S3 后端 + 预签名直链，R2 免出流量费 |

```
用户 ── Cloudflare DNS/CDN ──┬── Pages（前端静态）
                             └── 后端容器（Railway/Render/Fly）
                                    ├── Neon PostgreSQL（数据 + RLS）
                                    └── R2（PDF 等文件，预签名直链下载）
```

## 方案 A：前后端分离（CF Pages + 后端 PaaS）

1. **数据库**：Neon 建库 → 拿到连接串，改写成
   `postgresql+asyncpg://user:pass@host/db`。
2. **跑迁移**（必须，RLS 策略在迁移里）：
   `cd apps/backend && SCHOLARHUB_DATABASE_URL=<连接串> uv run alembic upgrade head`
3. **后端**：Railway/Render 新建服务，用仓库根 Dockerfile
   （`docker build -f apps/backend/Dockerfile .`），环境变量：

   | 变量 | 值 |
   |---|---|
   | `SCHOLARHUB_DATABASE_URL` | PG 连接串 |
   | `SCHOLARHUB_ENVIRONMENT` | `production` |
   | `SCHOLARHUB_SECRET_KEY` | `python -c "import secrets;print(secrets.token_hex(32))"` |
   | `SCHOLARHUB_FERNET_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
   | `SCHOLARHUB_ADMIN_PASSWORD` | ≥12 位强密码 |
   | `SCHOLARHUB_ALLOWED_HOSTS` | 后端域名，如 `api.example.com` |
   | `SCHOLARHUB_CORS_ORIGINS` | 前端域名，如 `https://scholarhub.pages.dev` |
   | R2（可选）：`SCHOLARHUB_STORAGE_BACKEND=s3` + S3 endpoint/key/secret/bucket | 指向 R2 的 S3 兼容端点 |

4. **前端**：CF Pages 连 Git 仓库，Root directory = `apps/frontend`，
   构建命令 `npm run build`，输出 `dist`；构建环境变量
   `VITE_API_URL=https://<后端域名>/api`。
5. **域名**：Cloudflare DNS 给后端加 CNAME → PaaS 分配的地址；开启代理（橙云）。

## 方案 B：单端口一体化（最省事）

后端容器直接托管前端静态文件（`SCHOLARHUB_STATIC_DIR` 已内置于
Dockerfile），一个服务搞定，前端走同源 `/api`，**无需 CORS**：

1. 按方案 A 步骤 1-3 部署后端容器（Dockerfile 已把 `dist/` 打进镜像并设好
   `SCHOLARHUB_STATIC_DIR`）。
2. Cloudflare DNS 把主域名指向该服务即可；前端不用单独部署。
3. 本地预览同款行为：`cd apps/backend && PORT=8000 uv run python deploy_server.py`。

> 方案 B 静态托管由 FastAPI 提供，无 CF 边缘缓存；流量大时可再加 CF 前置 CDN。

## 方案 C：VPS 单机全家桶 ⭐ 平台数最少、功能最完整

一台 VPS 跑全部（PostgreSQL + 后端 + 前端 + HTTPS），`docker-compose.yml` 已备好：

1. VPS 装 Docker + Compose v2，克隆仓库
2. `cp .env.example .env` → 填好 `SITE_DOMAIN` / `POSTGRES_PASSWORD` / 三个密钥（生成命令在文件注释里）
3. DNS A 记录：你的域名 → VPS IP
4. `docker compose up -d --build`
5. 验证：`curl https://$SITE_DOMAIN/api/health`

内置能力：Caddy 自动 HTTPS（Let's Encrypt，无需手工证书）、`alembic upgrade head` 随启动自动执行（RLS 就位）、`pgdata`/`uploads` 持久卷（数据与上传的 PDF 重启不丢）。功能 100% 完整：RLS、pg_trgm 搜索、文件持久、无冷启动、无平台配额。

成本参考：Hetzner CX22 / 腾讯云轻量 2C2G ≈ $4–5/月。可选：前面再套一层 Cloudflare 免费 CDN（只需把 NS 指到 CF）。

## 上线前 checklist

- [ ] `alembic upgrade head` 已在目标库执行（RLS 就位，`test_rls_coverage` 保证所有租户表都有策略）
- [ ] `SCHOLARHUB_ENVIRONMENT=production`（触发强密钥/ALLOWED_HOSTS 校验）
- [ ] SECRET_KEY / FERNET_KEY / ADMIN_PASSWORD 均为强随机值且**持久化**（重启不变）
- [ ] `SCHOLARHUB_ALLOWED_HOSTS` / `SCHOLARHUB_CORS_ORIGINS` 收紧到真实域名
- [ ] 首次登录后立即改 admin 密码 + 开启 TOTP（`/api/two_factor`）
- [ ] 健康检查：`GET /api/health` → `{"status":"ok"}`
- [ ] 文件存储用 R2/S3（容器本地盘会随重启丢文件）
