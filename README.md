<div align="center">

# ScholarHUB

**学术期刊发表与审稿平台**

让一个团队在一个下午搭起一个能投稿、能审稿、能发表、能让读者检索与订阅的期刊网站。

[![License](https://img.shields.io/badge/license-PolyForm--NC-red.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=white)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Code Style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4.svg?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

[![Lines of Code](https://img.shields.io/badge/lines_of_code-~30k-success)]()
[![Modules](https://img.shields.io/badge/modules-10-blueviolet)](#模块清单)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange)](#项目状态)

</div>

---

## 一句话定位

ScholarHUB 是一套**开箱即用的学术期刊发表平台**,把"投稿 → 审稿 → 录用 → 发表 → 阅读 → 订阅"这条主流程从零做完整,让你不用再为每个期刊/研究室/会议从零写一套定制系统。它不是一个论文写作工具,也不是文献管理软件,而是一个真正能跑、能给作者投递、能给编辑审稿、能给读者浏览的网站。

## 三类用户,三种身份

ScholarHUB 的所有功能都围绕这三类用户设计:

| 身份 | 在 ScholarHUB 上能做什么 |
|---|---|
| **作者** | 注册账号、登录后投递稿件、查看自己稿件的状态(待审/审稿中/录用/拒稿/已发表)、上传修改稿、回复审稿意见、查看已发表作品列表 |
| **编辑/审稿人(管理员)** | 在 admin 后台分配审稿人、提交审稿意见、录用/拒稿、组织卷期、把稿件从"录用"推到"已发表"、管理用户与角色、查看审计日志 |
| **读者** | 不登录就能浏览目录与文章元数据;登录后可阅读 PDF、订阅作者/学科、把文章加入个人阅读列表、接收订阅通知、获取个性化推荐 |

## 模块清单

ScholarHUB 把每个领域能力拆成独立模块,每个模块可以单独启用或替换。

| 模块 | 状态 | 描述 |
|---|---|---|
| `core` | ✓ shipped | 租户、用户、角色、模块注册表、admin shell、部署 |
| `catalog` | ✓ shipped | 文章元数据、学科、作者、期刊、卷期、tag |
| `submission` | ✓ shipped | 投稿 → 编辑分配 → 审稿 → 录用/拒稿 主流程 |
| `review` | ✓ shipped | OJS 风格审稿工作流、审稿意见、审稿人角色管理 |
| `reader` | ✓ shipped | 浏览器内 PDF 阅读、阅读进度、跨设备同步、大纲 |
| `export` | ✓ shipped | BibTeX / RIS / CSV / JSON 引用导出,支持往返 |
| `library` | ✓ shipped | 用户自己策展的阅读列表 |
| `follows` | ✓ shipped | 作者 / 学科订阅 + 通知 fan-out |
| `notifications` | ✓ shipped | 站内通知流、按用户隔离 |
| `ingest` | ✓ shipped | BibTeX/RIS/CSV 批量导入 + Crossref/arXiv 元数据抓取 |
| `recommendations` | ✓ shipped | 基于阅读历史的个性化推荐 + 推荐理由 |

## 技术栈

每一项都选用主流、长期可托管的方案,不放任何"冷门但很酷"的依赖。

### 后端

| 层 | 选型 |
|---|---|
| 语言 | Python 3.12+(`async/await` + 完整 type hints) |
| 框架 | FastAPI 0.115+ |
| ORM | SQLAlchemy 2(async) |
| 迁移 | Alembic |
| 数据库 | PostgreSQL 17(主库,启用 Row Level Security) |
| 校验 | Pydantic 2 + pydantic-settings |
| 鉴权 | JWT access + httpOnly cookie refresh;PyJWT + bcrypt |
| SSO | authlib(OIDC:Google / GitHub / Generic / Keycloak) |
| HTTP 客户端 | httpx |
| 邮件 | 可插拔:console(dev)/ SMTP relay(Mailgun / SendGrid / SES / Postmark) |
| 日志 | structlog(JSON 输出) |
| 工具链 | uv、ruff、mypy(strict)、pytest、pytest-asyncio、bandit、pip-audit |

### 前端

| 层 | 选型 |
|---|---|
| 框架 | React 19 |
| 语言 | TypeScript 5.7 |
| 构建 | Vite 7 |
| 路由 | TanStack Router v1(file-based + autoCodeSplitting) |
| 数据 | TanStack Query v5 |
| 状态 | Zustand(auth store) |
| UI | shadcn/ui + Radix primitives、Tailwind CSS v4 |
| 通知 | sonner toasts |
| 图标 | lucide-react |
| 工具链 | ESLint、Vitest、TypeScript Project References |

### 部署

| 项 | 选型 |
|---|---|
| 容器 | Docker Compose(dev + prod) |
| TLS | Caddy(自动 Let's Encrypt) |
| 数据库 | PostgreSQL 17-alpine |
| 镜像 | backend + frontend 同镜像,版本不会漂移 |

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                  前端 SPA  (apps/frontend)                    │
│   核心外壳  +  各模块贡献的路由 chunk                            │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP  +  httpOnly Cookie
┌──────────────────────────┴──────────────────────────────────┐
│                  后端 API  (apps/backend)                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  core:  租户 · 身份 · 角色 · 模块注册表 · admin · 部署    │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ 启动时按依赖顺序加载                  │
│  ┌────────┬────────┬─────┴────┬─────────┬─────────┬──────────┐ │
│  │catalog │review │submission│ reader  │ export  │follows   │ │
│  ├────────┼────────┼─────────┼─────────┼─────────┼──────────┤ │
│  │library │ingest  │recomm.  │notif.   │  ...    │          │ │
│  └────────┴────────┴─────────┴─────────┴─────────┴──────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
           PostgreSQL 17          (Redis: 规划中)
           (主库 + RLS)          (缓存 + 分布式限流)
```

**双层租户隔离** — 每个领域表都带 `tenant_id`:
1. 应用层:每个 SELECT/UPDATE/DELETE 显式追加 `Model.tenant_id == current_user.tenant_id`
2. 数据库层:PostgreSQL RLS 在 `get_db()` 中 `SET LOCAL app.current_tenant_id = :tid`,即使应用层漏写过滤,数据库也会拒掉跨租户行

## 快速开始

### 方式一:Docker Compose(推荐)

```bash
# 1. 生成强密钥
echo "SCHOLARHUB_SECRET_KEY=$(openssl rand -hex 32)" > .env
echo "SCHOLARHUB_ADMIN_PASSWORD=$(openssl rand -base64 18)" >> .env

# 2. 启动 dev stack(Postgres + backend)
docker compose -f infra/docker-compose.yml up --build

# 3. 打开 OpenAPI 文档
xdg-open http://localhost:8000/docs
```

### 方式二:本地裸跑(开发)

需要 Python 3.12+ 与一个 PostgreSQL 17 实例。

```bash
# 后端
cd apps/backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# 前端(另开一个终端)
cd apps/frontend
npm install
npm run dev
```

### 方式三:生产部署

```bash
# 1. 复制并填好生产 env
cp .env .env.prod
# 至少设置 SCHOLARHUB_SECRET_KEY 与 SCHOLARHUB_ADMIN_PASSWORD

# 2. 改 infra/Caddyfile,把 scholarhub.example.com 换成你的域名
# 3. 启动 prod stack(带 Caddy 自动 TLS)
docker compose -f infra/docker-compose.prod.yml -f docker-compose.override.yml \
  --env-file .env.prod up -d --build
```

> 邮件(Mailgun / SendGrid / SES / Postmark)与 OIDC SSO(Google / GitHub / Keycloak)的接入,见 [docs/integrations.md](docs/integrations.md)。

## 项目结构

```
scholarhub/
├── README.md                      # 本文件
├── CONTRIBUTING.md                # 贡献流程
├── SECURITY.md                    # 安全策略
├── LICENSE                        # PolyForm Noncommercial 1.0.0
├── VERSION                        # 单一版本号源
├── apps/
│   ├── backend/                   # FastAPI 服务(base + 模块)
│   │   ├── alembic/versions/      # 迁移文件,每模块一份
│   │   ├── app/
│   │   │   ├── api/               # 顶层路由(admin/auth/oidc/users/health/modules)
│   │   │   ├── core/              # 启动/配置/db/邮件/租户/tokens/security
│   │   │   ├── middleware/        # rate_limit / security_headers
│   │   │   └── modules/           # 10 个领域模块
│   │   ├── tests/                 # pytest + aiosqlite
│   │   └── pyproject.toml         # uv + ruff + mypy + bandit 配置
│   └── frontend/                  # React 19 SPA
│       ├── src/
│       │   ├── components/         # 通用 UI(shadcn 风格)
│       │   ├── hooks/api/          # 按模块分组的 React Query hooks
│       │   ├── lib/               # api client / auth store / types
│       │   └── routes/            # TanStack Router file-based 路由
│       └── package.json
├── docs/
│   ├── ARCHITECTURE.md            # 架构契约
│   └── integrations.md            # 邮件 + OIDC 接入
├── infra/
│   ├── Dockerfile.backend         # backend 镜像
│   ├── docker-compose.yml         # dev stack
│   ├── docker-compose.prod.yml    # prod stack(带 Caddy)
│   └── Caddyfile                  # TLS 模板
└── .github/
    ├── workflows/
    │   ├── ci.yml                  # ruff + mypy + pytest + RLS Postgres job + frontend
    │   └── gitleaks.yml            # 密钥扫描
    ├── dependabot.yml             # 自动依赖更新
    ├── CODEOWNERS                 # 代码归属
    └── ISSUE_TEMPLATE/            # issue 模板
```

## 配置(主要环境变量)

所有变量以 `SCHOLARHUB_` 为前缀,完整列表见 [`apps/backend/app/core/config.py`](apps/backend/app/core/config.py)。最关键的几项:

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `SCHOLARHUB_SECRET_KEY` | ✓ | JWT 签名密钥,至少 32 字符,`openssl rand -hex 32` 生成 |
| `SCHOLARHUB_ADMIN_PASSWORD` | ✓ | 首次启动创建的 admin 账户密码,至少 12 字符 |
| `SCHOLARHUB_DATABASE_URL` | | PostgreSQL 连接串,默认 `postgresql+asyncpg://scholarhub:scholarhub@localhost:5432/scholarhub` |
| `SCHOLARHUB_TENANCY_MODE` | | `single`(默认,单租户)/ `multi`(host-header 解析,未实现) |
| `SCHOLARHUB_ENVIRONMENT` | | `development`(默认)/ `staging` / `production` / `test` |
| `SCHOLARHUB_FRONTEND_BASE_URL` | | 邮件深链的 SPA origin,如 `https://app.yourdomain.com` |
| `SCHOLARHUB_OIDC_ENABLED` | | `true` 启用 OIDC SSO(配合下方 OIDC_* 变量) |
| `SCHOLARHUB_EMAIL_BACKEND` | | `console`(默认)/ `smtp` |
| `SCHOLARHUB_CORS_ORIGINS` | | 前端 origin 列表,逗号分隔 |

## 默认角色与权限

启动时 core 会自动创建以下角色(可在 admin 后台再分配):

| 角色 slug | 中文名 | 能做什么 |
|---|---|---|
| `admin` | 管理员 | 全部操作,含 admin 后台、用户管理、审计日志查看 |
| `editor` | 编辑 | 分配审稿人、组织卷期、录用/拒稿、把稿件推到"已发表" |
| `reviewer` | 审稿人 | 查看分配给自己的稿件、提交审稿意见 |
| `author` | 作者 | 投递稿件、查看自己稿件状态、上传修改稿 |
| `member` | 普通成员 | 阅读、收藏、订阅、查看个性化推荐 |

## CI / 测试

```bash
# 后端:lint + type + test
cd apps/backend
uv run ruff check .
uv run mypy app
uv run pytest -q

# 后端:RLS 隔离测试(需要真实 PostgreSQL)
SCHOLARHUB_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/test_rls_isolation.py -v

# 前端
cd apps/frontend
npm run lint
npm run typecheck
npm run build
npm run test
```

GitHub Actions workflow 见 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

## 项目状态

**版本**:0.1.0-alpha · **状态**:pre-alpha

10 个模块全部 shipped,前后端 + 数据库迁移 + 测试 + 部署都已就绪。后续规划:

- [ ] 多租户模式落地(host-header → tenant 映射表)
- [ ] Redis 接入(缓存 + 分布式限流)
- [ ] refresh token 显式 denylist
- [ ] 卷期(volume/issue)的高级管理界面
- [ ] DOI 注册与互链
- [ ] 全文检索(PostgreSQL FTS 或 Meilisearch)
- [ ] 文件存储从本地切换到 S3
- [ ] 工作流可视化(投稿 → 审稿 → 录用)

## 贡献

欢迎在 [GitCode 仓库](https://gitcode.com/badhope/scholarhub) 上提 issue 或 PR。流程与规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

Copyright © 2026 badhope. Released under the [PolyForm Noncommercial License 1.0.0](LICENSE).

**允许**(无需单独授权):

- 阅读、研究、审查本源码
- 把本软件用于个人、研究、教育、慈善、政府等**非商业**用途
- 为自己的非商业用途修改本软件,并在相同 PolyForm Noncommercial 条款下分发修改版

**不允许**(需书面授权):

- 任何**商业用途**(包括作为付费产品的一部分、托管为付费 SaaS、销售基于本软件的服务)
- 商业性修改或再分发

商业授权请联系:**badhope@noreply.gitcode.com**
