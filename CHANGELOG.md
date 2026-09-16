# Changelog

本文件记录 ScholarHUB 的可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 品牌物料升级:重绘 logo(`docs/assets/logo.svg` "S · 书页流转"一笔成型标志)、
  重建架构图(11 个模块 + core,修正旧图遗漏 `doi`/`recommendations`)与流程图
  (横向主流程 + 回流虚线 + 角色图例),新增前端 `BrandMark` 内联组件让侧边栏、
  移动端外壳、favicon 与文档用同一套几何。
- 新增界面截图与视频物料:`docs/assets/screenshots/` 19 张(17 桌面 1440×900 +
  2 移动 390×844)、`docs/assets/screenshots-overview.png` 总览图、
  `docs/assets/demo/ScholarHUB-promo.webm`(60s 宣传片:片头 + 中文字幕演示 + 片尾
  仓库地址)。视频用 VP9/WebM 而非 H.264/MP4:沙箱无 libx264,libopenh264 对
  UI 屏幕内容压缩效率低(60s 要 13 MB),VP9 同观感约 4 MB;不单独产出
  walkthrough —— 它与宣传片中间段完全重复,需要时删掉片头尾重跑即可。
- 新增可复现的媒体工具链 `apps/frontend/scripts/media/`:
  `seed-and-record.mjs`(8 篇演示资源)、`seed-submissions.mjs`(3 位作者投稿 +
  分配/接受/评审全流程)、`seed-reader-data.mjs`(阅读列表/关注/订阅/阅读历史)、
  `seed-more-resources.mjs`(补未读资源,幂等)、`shoot-screenshots.mjs`(19 张截图)、
  `record-usage.mjs`(平稳滚动的流程录像)、`build-promo.sh`(ffmpeg 合成)、
  `contact_sheet.py`(拼总览图)。
- `e2e_run_server.py` 支持 `E2E_KEEP_DB=1` 保留既有数据库:截图/录屏场景需要
  "先灌演示数据再重启后端加载新代码",默认行为(每次重建)不变。

### Fixed

- 推荐页在**已读完全部资源**时返回空列表 → 改为回退到最新收录
  (`reason="you have read everything; showing latest"`),不再把用户带进死胡同;
  前端对应把 `score === 0` 的条目显示为"最新收录 · 阅读后可获得个性化推荐"
  并把进度条标签切成"推荐依据 / 最新",不再谎报 0% 匹配度。

- 新增部署指南 `docs/DEPLOYMENT.md`:服务器规格建议、首次部署逐步操作、邮件/密钥轮换/
  对象存储等生产配置、备份与升级流程、故障排查表,并明确回答"是否需要 Cloudflare 等
  云服务"(不需要,单机 Docker Compose + Caddy 自动 HTTPS 即可)。
- 新增 GitHub 治理模板:bug/feature 的 ISSUE_TEMPLATE 与 PR 模板(含 CI 门禁速查)。
- 新增 `scripts/check-version.sh` 版本一致性校验(VERSION / pyproject / package.json /
  `app.__version__` 四处必须同步),已纳入 CI `backend` job 首步。
- CI 新增 `e2e` job:此前 66 个 E2E 用例在 CI 上完全不可见(核心业务链路零覆盖),
  现在 node 20 + uv + chromium 全量跑通并上传 playwright-report 产物。

### Fixed

- 修复 `/catalog` 与 `/submissions` 表格无列宽约束导致的横向溢出(1280px 视口下
  catalog 表实际宽 2025px):长文本列(标题/作者/学科)按 shadcn DataTable 惯例加
  `max-w + truncate`,状态/时间/操作列在桌面视口完整可见。
- 修复详情页阅读进度卡渲染原始 ISO 时间戳(`2026-09-14T14:21:51…Z` 撑破卡片):
  统一走 `toLocaleString()` 格式化,`MetaItem` 值加 `min-w-0 truncate` 防御超长。
- 修复"编辑工作台"(`/submissions/pending`)侧边栏误高亮"我的提交":新增独立导航项
  (admin-only,挂审稿工作台旁),高亮算法改为最长前缀胜出;移动端"更多"抽屉同步补入口。
- 侧边栏 admin 组菜单归组:期刊四件套(卷/期/信息/设置)连续排列,审计日志垫底。
- Cookie 同意横幅层级从 z-50 降至 z-40:模态弹窗(Radix Dialog overlay z-50)压住
  横幅由层级保证,不再依赖 DOM 顺序。
- **修复后端覆盖率测量系统性失真**:SQLAlchemy async 通过 greenlet 调同步 DBAPI,
  未声明 `coverage.run.concurrency` 时 tracer 会在 greenlet 切回后丢帧,导致所有 async
  处理函数在第一个 `await` 之后的整段代码被误判为"未覆盖"。实测该项使 TOTAL 从
  真实 84% 虚低到 64%（虚低 20 个点),此前所有覆盖率结论与 CI 门槛都基于错误数据。
- 修复 `vite.config.ts` 类型错误阻塞 CI frontend job:`coverage.all` 在 Vitest 4 已移除
  (改为 `include` 枚举全部文件),保留该键会让 `tsc` 报 TS2769。

### Tests

- 新增 5 个后端测试文件(共 144 个用例),后端测试数 499 → 643(后续 +1 至 644):
  `test_doi.py`(30)/`test_webauthn.py`(23)/`test_ingest_fetchers.py`(37)/
  `test_ingest_parsers.py`(24)/`test_tenant_middleware.py`(17)/
  `test_token_denylist_redis.py`(13)。
- 后端覆盖率 64% → 84%,CI 门槛 `--cov-fail-under` 从 62 上调至 80。
  重点模块:`webauthn.py` 20%→100%,`doi/routes.py` 32%→100%,
  `doi/registration.py` 20%→98%,`ingest/fetchers.py` 37%→97%,
  `ingest/parsers.py` 77%→96%,`tenant.py` 56%→93%,`token_denylist.py` 59%→89%。
- 新增 3 个前端测试文件(共 24 个用例),前端测试数 76 → 100,
  覆盖率 9.3% → 13.0%:`api.test.ts`(9,含并发 401 共用一次 refresh 的竞态回归)/
  `monitoring.test.ts`(7)/`meta-item.test.tsx`(8)。
- 新增推荐模块用例 `test_all_read_falls_back_to_latest`,后端测试数 643 → 644。
- 抽出纯函数便于测试:`lib/nav.ts`(`resolveActiveNavPath`,最长前缀高亮的回归保护)、
  `components/common/meta-item.tsx`(详情页截断契约)、`lib/utils.ts::formatDateTime`。
- 开启 pytest 严格模式(`--strict-markers --strict-config`),避免拼错 marker 导致用例
  被静默跳过而假绿。

## [0.2.0] - 2026-09-14

> 主题：移动端体验 + 发布链路加固。新增移动端专用外壳与四区域适配；修复模型/迁移
> 结构性漂移（生产库缺失的 `doi_registrations` 表）等 20+ 项缺陷；CI 新增迁移门禁、
> 依赖漏洞审计与版本一致性校验，前端 70 单测、E2E 66 用例全量入网。

### Added

- 新增移动端独立专用外壳(`MobileAppShell`):底部 4 Tab + 中心 FAB + "我的"底部抽屉,
  运行时按视口宽度切换,与桌面侧边栏完全独立,非响应式裁剪。
- 目录浏览、仪表盘、详情页、阅读页四个区域做了移动专属设计与适配:
  卡片流(非表格)、2 列大块+快捷操作、固定底部操作栏。
- 新增 Playwright `mobile` 项目(iPhone 13 视口)与 `mobile-shell.spec.ts` 5 个 E2E 用例。
- E2E 测试套件更新至 12 个 spec(56 chromium + 5 mobile,含 4 个共用 mobile/chromium 的用例)。
- 新增 `npm run test:e2e` 脚本,便于新贡献者发现和执行 Playwright 测试。
- 新增 `VERSION` 文件,声明项目版本 0.1.0。
- 新增 `.github/workflows/ci.yml`:PR/push 自动跑 lint、typecheck、单元测试、后端 pytest。
- 新增 `.vscode/extensions.json`:推荐项目开发所需 VS Code 扩展。
- 以 GitCode 仓库 `badhope/scholarhub` 为主托管渠道,Gitee `badhope/scholarhub` 为同步镜像
  (历史说明:项目早期曾以 GitHub `Morningstar202604/scholarhub` 为唯一渠道,现已迁移)。
- 新增项目 LOGO、投稿-审稿-发表流程图、系统架构图(均位于 `docs/assets/`)。
- 新增 `CHANGELOG.md`、`CODE_OF_CONDUCT.md`、`SUPPORT.md`,补齐开源治理配套。
- 新增 `scripts/dev.sh`:一键冷启动 dev 栈(PostgreSQL + 后端 + 前端),自动执行
  Alembic 迁移、按需生成带随机密钥的 `apps/backend/.env`、统一托管日志与 pid 文件。
- 新增 `scripts/doctor.sh`:开发环境自检(工具链版本、PostgreSQL 连通性、`.env`
  是否仍为占位符、端口占用、Alembic head 数量),以退出码表达是否存在阻断项。
- 新增 Alembic 合并 revision `20d879058fa2`,将长期并存的两个迁移分支收敛为单个 head。
- 新增迁移 revision `019_doi_schema_drift`,补建生产库缺失的 `doi_registrations` 表
  (含 RLS 与 4 个索引),并修复 `users.orcid` 列宽、`reading_list_items.tenant_id` 外键两处漂移。
- 新增 CI `migrations` job:在 PostgreSQL 17 service 上执行 `alembic upgrade head` +
  `alembic check`,模型与迁移一旦漂移即红——修复单测用 `create_all` 建表、永远测不到
  迁移路径的结构性盲区。
- CI `security` job 的 Bandit 门槛从 `--severity-level medium` 收紧至 `low`(代码已零告警,
  任何新增发现直接失败,防止静默回潮);`frontend` job 补跑此前从未执行的 70 个 vitest 单测。
- 仓库同时托管于 GitCode(主)与 Gitee(镜像),两远端保持分支/标签/HEAD 同步。

### Fixed

- 修复模型/迁移结构性漂移(P0):`doi_registrations` 表在模型中声明但从未被任何迁移创建,
  生产库 `alembic upgrade head` 后无此表,DOI 全部接口必然 500;单测因走 `create_all`
  建表路径而全部绿灯,完全掩盖该缺陷。已由迁移 `019_doi_schema_drift` 补建(含 RLS)。
- 修复 `users.orcid` 数据库列宽 `VARCHAR(20)` 与模型 `String(200)` 不一致;修复
  `reading_list_items.tenant_id` 缺失外键(租户删除会遗留孤儿行)。
- 修复 `doi` 模型 `registered_by` 声明矛盾:`ondelete="SET NULL"` 与 `nullable=False`
  并存,删除用户时必然违反非空约束;按 append-only 审计语义改为可空。
- 修复 5 处模型 metadata 与真实 schema 不一致导致的 `alembic check` 误报:`users` 复合
  索引 `ix_users_tenant_orcid`、`users.deleted_at` 单列索引、`notifications` 复合索引
  `ix_notifications_user_id_created_at`、`reading_history.viewed_at` 索引此前均只由迁移
  创建而模型未声明;`tenants.slug` 与 `submission_versions` 的唯一约束改用命名
  `UniqueConstraint` 声明,与迁移产物对齐。
- 修复 `vite.config.ts` vitest 配置未排除 `tests/e2e/` 目录,导致 `vitest run`
  误将 Playwright spec 当作 vitest 用例执行(10 条虚假失败)。
- 修复 `admin-user-management.spec.ts` 禁用账号后重新打开下拉菜单时的 Radix
  内部状态残留问题:缺少 Escape 确认关闭步骤,导致 trigger 二次点击行为异常
  (实测导航至 `/verify-email` 页面)。对齐同文件通过用例的稳健写法。
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
- 修复 `alembic upgrade head` 因多 head 而失败:11 个模块各自维护迁移分支,形成
  `018_user_webauthn` 与 `51688fb04bf7` 两个 head。README 快速开始与
  `Dockerfile.backend` 的 CMD 都使用该命令,导致官方 Docker 部署在建库阶段即中断。
- 修复 `app/api/two_factor.py` 用 `assert` 校验 `backup_code`:`python -O` 会移除断言,
  2FA 认证路径改为显式判空并返回 422。
- 修复 4 处 Starlette 过时常量 `HTTP_422_UNPROCESSABLE_ENTITY`
  (改用 `HTTP_422_UNPROCESSABLE_CONTENT`),消除弃用警告。
- 修复 3 处 httpx per-request cookies 弃用写法:改为在 client 实例上设置 cookie,
  并在 `finally` 中清理,避免污染共享 fixture。
- 补齐 `infra/docker-compose.yml` 缺失的 frontend 服务(Vite dev, 5173),并让
  `vite.config.ts` 的 `/api` 代理目标支持 `VITE_PROXY_TARGET` 环境变量,
  使容器内可指向 `backend` 服务名而非 `localhost`。
- 补齐 zh / ja README 缺失的 Security 章节,与英文版结构对齐。
- 填写三语 README 空白的 Repository / 仓库地址 / リポジトリ 章节。
- 修正三语 README 单元测试数量徽章(410 → 479),并补充前端 70 / E2E 64 的实际规模。

### Security

- 消除 bandit 全部 9 个 Low 告警:5 处 `except Exception: pass` 改为
  `logger.debug(..., exc_info=True)`,在不影响请求的前提下保留排障线索;
  2 处测试专用密钥加 `# nosec B105` 标注,并说明其受「仅 test 环境生效」与
  「弱密钥黑名单」双重保护。

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

[Unreleased]: https://gitcode.com/badhope/scholarhub/compare/v0.2.0...HEAD
[0.2.0]: https://gitcode.com/badhope/scholarhub/compare/v0.1.0...v0.2.0
[0.1.0]: https://gitcode.com/badhope/scholarhub/releases/tag/v0.1.0
