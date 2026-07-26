# Changelog

本文件记录 ScholarHUB 的可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added (security hardening M1.5 / M2 / M3 / M4 / M5)

- **M1.5 OIDC providers 端点**: 新增 `GET /api/auth/oidc/providers`,
  列出当前后端允许的 OIDC provider 列表。启动时前端 fetch 此端点,
  避免硬编码 provider 名 / 允许列表。强制 PKCE;`state` 参数是
  短 JWT (CSRF 防御)。
- **M2 TOTP 双因素认证**: RFC 6238 TOTP,密钥 Fernet 加密落库,
  10 个一次性备用码 (bcrypt hash)。完整流程
  `setup → verify-setup → /auth/2fa/authenticate → 完整令牌签发`,
  含 `two_factor_token` (5 分钟一次性 JWT)。
- **M3 JWT 密钥轮换**: `app/core/key_rotation.py` 维护有序密钥链,
  编码走最新密钥,解码遍历活跃链。`POST /api/admin/reload-secret-keys`
  触发运行时热加载,无需重启进程。配置项
  `SCHOLARHUB_PREVIOUS_SECRET_KEYS` 支持逗号分隔多密钥。
- **M4 限流抽象层**: `app/core/rate_limit_store.py` 暴露
  `RateLimitStore` 接口,默认 `MemoryRateLimiterStore`,
  设置 `SCHOLARHUB_REDIS_URL` 时切换到 `RedisRateLimiterStore`
  (Lua 原子 INCR+EXPIRE)。Redis 不可用自动降级到内存 (fail-open),
  拒绝的请求不延展锁定期。
- **M5 GDPR 端点**: `GET /api/users/me/export` (数据可携带) +
  `DELETE /api/users/me` (软删除 + 30 天 grace,PII 原地匿名化 +
  token_version bump) + `POST /api/users/me/restore` (grace 期内
  撤销删除,过期返回 410 Gone)。
- **CI/CD pipeline**: 新增 `.github/workflows/{ci,release,dependabot-auto-merge}.yml`。
  - `ci.yml`: backend ruff+format+mypy+pytest+pip-audit, frontend
    eslint+tsc+vitest+build, secret scan (gitleaks), CodeQL 静态分析
    (Python + JavaScript)。
  - `release.yml`: 推送 `v*.*.*` tag 自动构建 wheel + GHCR 镜像 +
    起草 GitHub Release。
  - `dependabot-auto-merge.yml`: patch / minor 依赖更新自动 squash。
- **本地开发**: `.pre-commit-config.yaml` (gitleaks + ruff + eslint)、
  `.gitleaks.toml` (项目定制规则集)、`scan_secrets.py` (一键扫描)。
- **依赖**: backend 同步到 100 个 lock 包 (fastapi 0.139.2 等),frontend
  同步 minor 升级 (vite 7.3.6、tailwindcss 4.3.3 等)。

### Added (Round 2 — production engineering + privacy + auth hardening)

- **P0-A 生产工程化.** `/metrics` Prometheus 端点 + structlog 上下文绑定
  (request_id/tenant_id/user_id) + `/healthz` `/livez` `/readyz` 健康检查拆分 +
  SQLAlchemy 连接池 metrics + fakeredis 限流存储测试。
- **P1-A 隐私合规.** `/privacy` 静态端点 + cookie consent banner 前端组件 +
  审计日志保留期 365 天常量 + admin 强制 2FA gate (`require_2fa_for_admin` 配置项)。
- **P1-B 认证加固.** `/api/auth/revoke-all` 全量令牌撤销 + CSRF 双重提交 cookie
  (默认关闭) + captcha hook 抽象 (`CaptchaVerifier` Protocol, 默认关闭)。
- **P2-A RFC 7807.** 所有 HTTP 异常返回 `application/problem+json`,
  含 `type`/`title`/`status`/`detail`/`instance` 字段。
- **P2-B 学术领域.** `User.orcid` 字段 + `Resource.authors_meta` 支持 ORCID;
  `Discipline`/`Subdiscipline` 本体表 (alembic 015) + CRUD 端点;
  Crossref 反查增强 (`publisher`/`short_container_title`/`volume`/`issue`/`page`/`ISSN`, alembic 016)。
- **安全核心测试.** `test_secret_validation.py` (14 用例, Settings 密钥强校验) +
  `test_totp_algorithm.py` (24 用例, RFC 4226 附录 D 向量 + Fernet 加密往返) +
  `test_security_headers.py` (7 用例, CSP/HSTS/X-Content-Type 等) +
  `test_captcha_hook.py` + `test_csrf_and_revoke.py` (7 用例) +
  `test_problem_json.py` (3 用例) + `test_privacy_and_2fa_admin.py` (6 用例) +
  `test_orcid.py` + `test_ontology.py` (12 用例) + `test_metrics.py` (7 用例) +
  `test_context_binding.py`。
- **CI 门禁.** `ci_local.ps1`/`ci_local.sh` 本地镜像脚本; ruff 全域通过;
  mypy strict 84 文件零错误; ruff format 全域通过; bandit 低严重度扫描。
- **依赖升级.** backend uv.lock + frontend package-lock.json 同步 latest minor releases。

### Added (其他)

- 新增 GitHub 长镜像仓库 `weed33834/scholarhub`,与 GitCode 主结同步发布。
- 新增项目 LOGO、投稿/审稿-发表流程图、系统架构图(均位于 `docs/assets/`)。
- 新增 `CHANGELOG.md`、`CODE_OF_CONDUCT.md`、`SUPPORT.md`, 琛拉贵开源治理配好。
- E2E 测试套件 56 个 spec, 覆盖作者 / 编辑 / 审稿 / 读者 / 期刊五类角色的完整旅程。
- 新增 `.github/SECURITY-MONITORING.md` (安全自动化层级文档).

### Fixed

- 修复 `reader/$resourceId` 在新用户首次打开阅读页时进度无法上报的问题
  (`hasSyncedRef` 改用 `progress.isFetched` 判断 query 完成)。
- 修复 axios 数组参数序列化与 FastAPI `list[int] = Query()` 不匹配导致的引用导出 400。
- 修复 E2E 后端在 test 模式下 bootstrap 跳过导致 admin 账户未创建的问题。
- 修复 E2E 顺序运行触发 `/api/auth/login` 限流(10/min)导致后续测试全部 429。
- 修复 SQLAlchemy 2 async + aiosqlite 在 `commit` 阶段抛 `IntegrityError` 被包成
  `greenlet_spawn` 错误, 导致 `except IntegrityError` 不触发的问题(改用 `flush`)。
- 修复 `db.rollback()` 后 ORM 属性 expire 在 async 上下文访问会触发同步 lazy-load 的问题
  (改用局部变量缓存 `user_id`/`tenant_id`)。
- 修复 React StrictMode 双挂载时初始 state 覆盖服务端实际进度的问题。
- 修复 `AnyHttpUrl` 类型在 SQLite DBAPI 上无法绑定的问题(统一 `str()` 转换)。
- 修复 DialogContent 长表单超出 viewport 的问题。
- 修复 TanStack Router Devtools 浮层拦截 E2E 点击的问题(E2E 时通过
  `navigator.webdriver` 隐藏)。
- 修复 Radix DropdownMenuCheckboxItem 残留 menu 导致后续点击被 portal 拦截的问题。
- 修复 Playwright strict mode 误匹配(用 `{ exact: true }`、`getByRole('heading')`、
  `aria-label` 等精确选择器替代 `getByText`)。
- 修复 Blob URL `<a download>.click()` 在 Playwright 中 `waitForEvent('download')` 不可见
  的问题(改用 `waitForResponse` 监听 backend 响应)。
- 修复前端 TypeScript strict 模式下 `useAuthenticateTwoFactor` 命名导入未使用
  报错(从 `two-factor-section.tsx` 移除)。

## [0.1.0] - 2026-07

### Added

- **core** 模块: 租户、用户、角色、模块注册表、admin shell、部署脚本。
- **catalog** 模块: 文章元数据、学科、作者、期刊、卷期、tag。
- **submission** 模块: 投稿 → 编辑分配 → 审稿 → 录用/拒稿主流程。
- **review** 模块: OJS 风格审稿工作流、审稿意见、审稿人角色管理。
- **reader** 模块: 阅读器内 PDF 阅读、阅读进度、跨设备同步、阅读历史。
- **export** 模块: BibTeX / RIS / CSV / JSON 引用导出, 支持本地。
- **library** 模块: 用户自策展的阅读列表。
- **follows** 模块: 作者 / 学科订阅 + 通知 fan-out。
- **notifications** 模块: 站内通知流, 按用户隔离。
- **ingest** 模块: BibTeX/RIS/CSV 批量导入 + Crossref/arXiv 元数据抓取。
- **recommendations** 模块: 基于阅读历史的个性化推荐 + 推荐理由。
- 双层租户隔离: 应用层 filter + PostgreSQL Row Level Security。
- JWT 鉴权: access token (短时, sessionStorage) + refresh token (httpOnly cookie)
  + token_version 刷置换。
- 邮件后端可插拔: console (dev) / SMTP relay (Mailgun / SendGrid / SES / Postmark)。
- OIDC SSO: Google / GitHub / Generic / Keycloak。
- Docker Compose dev + prod 部署, Caddy 自动 TLS, Alembic 迁移在容器启动时执行。
- CI: GitHub Actions 跑 ruff + mypy + pytest + RLS Postgres + 前端 lint/typecheck/build/test。
- gitleaks 密钥扫描 CI。
- 安全中间件: CSP、HSTS、X-Frame-Options、X-Content-Type、Referrer-Policy、Permissions-Policy。
- 启动器 `secret` 校验: 非 test 环境强制拒绝弱密钥 / 弱密码。
- 审计日志: 每个 admin 操作按租户记录。

[Unreleased]: https://github.com/weed33834/scholarhub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/weed33834/scholarhub/releases/tag/v0.1.0