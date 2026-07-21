# Changelog

本文件记录 ScholarHUB 的可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 新增 GitHub 镜像仓库 `weed33834/scholarhub`,与 GitCode 主仓同步发布。
- 新增项目 LOGO、投稿-审稿-发表流程图、系统架构图(均位于 `docs/assets/`)。
- 新增 `CHANGELOG.md`、`CODE_OF_CONDUCT.md`、`SUPPORT.md`,补齐开源治理配套。
- E2E 测试套件 56 个 spec,覆盖作者/编辑/审稿人/读者/访客五类角色的完整旅程。

### Fixed

- 修复 `reader/$resourceId` 在新用户首次打开阅读页时进度无法上报的问题:`hasSyncedRef`
  改用 `progress.isFetched` 判断 query 完成;手动"保存进度"按钮绕过 guard,确保在
  GET /progress 仍在 retry 时也能立即上报用户输入。
- 修复 axios 数组参数序列化与 FastAPI `list[int] = Query()` 不匹配导致的引用导出 400。
- 修复 E2E 后端在 test 模式下 bootstrap 跳过导致 admin 账户未创建的问题。
- 修复 E2E 顺序运行触发 `/api/auth/login` 限流(10/min)导致后续测试全部 429。
- 修复 SQLAlchemy 2 async + aiosqlite 在 `commit` 阶段抛 IntegrityError 被包成
  `greenlet_spawn` 错误,导致 `except IntegrityError` 不触发的问题(改用 `flush`)。
- 修复 `db.rollback()` 后 ORM 属性 expire,在 async 上下文访问会触发同步 lazy-load 的问题
  (改用局部变量缓存 `user_id`/`tenant_id`)。
- 修复 React StrictMode 双挂载时初始 state 覆盖服务端真实进度的问题。
- 修复 `AnyHttpUrl` 类型在 SQLite DBAPI 上无法绑定的问题(统一 `str()` 转换)。
- 修复 DialogContent 长表单溢出 viewport 的问题。
- 修复 TanStack Router Devtools 浮层拦截 E2E 点击的问题(E2E 时通过 `navigator.webdriver` 隐藏)。
- 修复 Radix DropdownMenuCheckboxItem 残留 menu 导致后续点击被 portal 拦截的问题。
- 修复 Playwright strict mode 误匹配(用 `{ exact: true }`、`getByRole('heading')`、
  `aria-label` 等精确选择器替代 `getByText`)。
- 修复 Blob URL `<a download>.click()` 在 Playwright 中 `waitForEvent('download')` 不可靠
  的问题(改用 `waitForResponse` 监听 backend 响应)。

## [0.1.0] - 2026-07

### Added

- **core** 模块:租户、用户、角色、模块注册表、admin shell、部署脚本。
- **catalog** 模块:文章元数据、学科、作者、期刊、卷期、tag。
- **submission** 模块:投稿 → 编辑分配 → 审稿 → 录用/拒稿主流程。
- **review** 模块:OJS 风格审稿工作流、审稿意见、审稿人角色管理。
- **reader** 模块:浏览器内 PDF 阅读、阅读进度、跨设备同步、阅读历史。
- **export** 模块:BibTeX / RIS / CSV / JSON 引用导出,支持往返。
- **library** 模块:用户自策展的阅读列表。
- **follows** 模块:作者 / 学科订阅 + 通知 fan-out。
- **notifications** 模块:站内通知流,按用户隔离。
- **ingest** 模块:BibTeX/RIS/CSV 批量导入 + Crossref/arXiv 元数据抓取。
- **recommendations** 模块:基于阅读历史的个性化推荐 + 推荐理由。
- 双层租户隔离:应用层 filter + PostgreSQL Row Level Security。
- JWT 鉴权:access token (短时, sessionStorage) + refresh token (httpOnly cookie)
  + token_version 双轮换。
- 邮件后端可插拔:console (dev) / SMTP relay (Mailgun / SendGrid / SES / Postmark)。
- OIDC SSO:Google / GitHub / Generic / Keycloak。
- Docker Compose dev + prod 部署,Caddy 自动 TLS,Alembic 迁移在容器启动时执行。
- CI:GitHub Actions 跑 ruff + mypy + pytest + RLS Postgres + 前端 lint/typecheck/build/test。
- gitleaks 密钥扫描 CI。
- 安全中间件:CSP、HSTS、X-Frame-Options、X-Content-Type、Referrer-Policy、Permissions-Policy。
- 防御性 secret 校验:非 test 环境强制拒绝弱密钥/弱密码。
- 审计日志:每个 admin 操作按租户记录。

[Unreleased]: https://github.com/weed33834/scholarhub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/weed33834/scholarhub/releases/tag/v0.1.0
