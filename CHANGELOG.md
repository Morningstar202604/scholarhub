# Changelog

本文件记录 ScholarHUB 的可见变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Security

- **TOTP 重放防线接线**（T2 白盒探测发现）：`verify_totp` 的 `last_counter` 参数此前
  从未被传入、`totp_last_used_counter` 只存在于文档字符串——同一 30s 窗口内的验证码
  可被重复使用。新增 `users.totp_last_used_counter` 列（迁移
  `022_user_totp_last_used_counter`），verify-setup 落记首用计数器，`/auth/login/2fa`
  与 `/auth/2fa/authenticate` 两条完成路径接入重放校验并持久化。
- **GDPR 宽限期恢复不可达**：删除会 bump `token_version`，restore 端点对删除前 token
  必然 401——文档承诺的 30 天恢复对所有真实用户结构性失效。restore 现在对
  「软删 + 宽限窗口内」豁免版本校验（删除时密码已匿名化，删除前 token 是唯一凭证；
  restore 会重打 token_version，使包括攻击者持有的在内的所有旧 token 失效）。
- **`/auth/2fa/authenticate` 补租户过滤**：用户查询此前不带 tenant 条件（兄弟路径
  `/auth/login/2fa` 一直有），SQLite/无 RLS 部署下 A 租户铸造的 pending token 可在
  B 租户完成 2FA。生产 PG+RLS 不受影响，本次对齐防御纵深。
- **审稿报告创建状态码 200 → 201**（REST 语义）。

  回归：backend 644 passed / 1 skipped；生产冒烟 smoke.sh 8/8；T2 白盒探针
  62 用例 0 FINDING（真实进程实测）。

### Fixed

- **全库逐行审查（8 路并行 × 约 2.5 万行）后修复的缺陷批次**：

  - **安全**：`app/main.py` 静态回退的路径穿越（`startswith` 前缀匹配会让相邻目录
    `/srv/app/static-dev` 通过校验，改为 `is_relative_to`）；2FA 设置页不再把含 TOTP
    密钥的 `otpauth://` URI 发给第三方二维码服务（密钥明文外泄，且离线时开启流程
    必失败），改由本地 `qrcode.react` 渲染。
  - **2FA 双轨归一**：删除明文 `two_factor_*` 列组与 `/api/users/me/2fa/*` 端点，
    统一到加密版 `totp_*` + `/api/auth/2fa/*`;登录闸门与管理员闸门改读同一来源
    （此前两套列各认一半——走 `/auth/2fa` 报名的用户登录不触发挑战，走
    `/users/me/2fa` 报名的管理员被 403 锁死）。迁移 `021_unify_two_factor` 搬运
    存量报名数据后 DROP 废弃列组，并顺带删除从未接线的 `resource_stats` 死表。
  - **签名密钥热轮换**：`core/tokens.py`、`core/totp.py` 改用 `get_settings()`。
    此前绑定模块级 settings 单例，`/api/admin/security/reload` 轮换密钥后，邮箱验证 /
    密码重置 / 2FA 待验证令牌仍用旧密钥签发与校验。
  - **S3 预签名 URL**：删除在 URL 后追加 `&range=` 的透传——给 SigV4 预签名 URL 加
    未签名参数会得到 `SignatureDoesNotMatch`，S3 路径上的 PDF 翻页/断点续传全挂。
    S3 本就原生识别客户端的 `Range` 头，无需转发。
  - **投稿创建 500**：`download_url` / `external_url` 是 pydantic `AnyHttpUrl`，直接赋给
    `String` 列会被 asyncpg 拒绝；改为显式 `str()` 后落库（更新路径早已这么做）。
  - **全文搜索静默退化**：Meilisearch 过滤表达式的 `tenant_id` 补引号（原先只有
    `type`/`discipline` 走 `_quote`），UUID 租户下解析失败会被吞掉并整体退化成数据库
    ILIKE。
  - **审计与通知并入主事务**：submission / review 的 5 处 handler 原先把审计日志写在
    主 `commit()` 之后的第二个事务里（注释却宣称「并入主事务」），第二个 commit 失败
    即丢审计；统一改为一次提交。
  - **前端**：公开端点（登录/注册/重置密码）的 401 不再误触发 `/auth/refresh`，也不
    再用 refresh 错误覆盖原始错误（登录页此前看到的是通用报错）；`/settings` 补登录
    守卫；仪表盘两张统计卡改为「我的投稿」（原「我的提交」走的是编辑专属的
    `/submissions/pending`，非编辑永远 403 显示「—」）与「未读通知」（原显示的是通知
    总数）；三个列表 hook 的 query key 补上分页参数（此前翻页后 60 秒内显示上一页
    数据）；重投后失效版本历史；目录页多选随翻页/筛选重置。
  - **权限与状态码**：编辑可查看单篇投稿（原先能决定却不能 GET）、审稿报告对已分配
    审稿人开放、指派审稿时校验目标用户持有审稿人角色；catalog 子学科 slug 重复回
    409 而非 500。
  - **输入校验**：`ResourceUpdate.authors` 复用 `Authors` 注解（PATCH 原先跳过逐元素
    校验，可写入空串或超长作者）；`authors_meta` 长度与 `authors` 一致；follows 超长
    学科名回 422 而非 404。
  - **导出**：`?ids=1&ids=1` 按输入顺序去重；BibTeX 标题/摘要转义 LaTeX 特殊字符
    （未转义的花括号会截断整条文献表），DOI/URL 保持原样。
  - **抓取**：OpenAlex DOI 分支保留路径中的 `/`（原先编码为 `%2F`，上游按未知 ID
    处理，等于每次 DOI 抓取都 404）。
  - **部署**：`infra/docker-compose.prod.yml` 四处凭证/密钥插值由弱默认值改为必填
    `:?`，缺变量硬失败（根 compose 一直是这个口径，生产栈反而放行弱凭据）；
    `backup.sh`/`restore.sh` 去掉 `pg_dump --format=custom` 之外的多余 gzip 层；根
    compose 注释纠正为「读取仓库根 .env」;`alembic/env.py` 不再静默吞掉 `load_all()`
    异常（会让 `alembic check` 真空通过）。
  - **其他核心**：SMTP `use_tls` 真正生效（原先只存不用，隐式 TLS 端口 465 无法工作）；
    captcha verifier 加载器支持其文档承诺的两种形式并做缓存；租户 GUC 改用参数化
    `set_config()`；限流拒绝计数器接上 `.inc()`（此前 Prometheus 上是个假指标）；
    `close_rate_limiter_store()` 接入 lifespan 收尾（Redis 客户端此前不关闭）。

### Removed

- 死代码清理（均经全仓引用检索确认无消费者）：`core/retention.py` 的两个未调用
  截止时间函数、`core/captcha.py` 的空依赖、`core/tenant.py` 的未用 uuid 生成器与类型
  别名、`core/modules.py` 的 `get()`/`__contains__`、`doi/registration.py` 的
  `DATACITE_BASE_URL`/`_xml_headers`/`get_doi_metadata`（含其 6 条测试）、
  `submission` 的两处 `_ = ResourceCreate(...)` 死校验与 `ReviewRecommendation` 别名、
  导出路径的不可达 `except ValueError`、follows/notifications/library 四个未使用的
  `user` relationship（默认懒加载，async 下误访问即抛 greenlet_spawn）、前端约 120 行
  无消费者导出、`ResourceStat` 模型与 `resource_stats` 表。
- 复制粘贴去重：错误提取统一走 `extractError`、目录筛选字段抽 `CatalogFilterFields`、
  blob 下载抽 `downloadBlob`、列表解析抽 `parseListField`、页码推断抽
  `inferTotalPagesFromFullPage`、catalog 本体校验抽 `validate_ontology`。

### Added

- **单端口一体化部署**:`apps/backend/Dockerfile` 多阶段构建把前端 `dist/` 打进后端镜像
  (`deploy_server.py` 同源托管 SPA + API,无 CORS),任意 Docker PaaS(Render / Railway /
  Fly)一个服务跑全栈;容器启动自动执行 `alembic upgrade head`(RLS 随启动就位)。
- **VPS 单机全家桶**:仓库根 `docker-compose.yml`(PostgreSQL 17 + 后端 + Caddy 自动
  HTTPS、`pgdata`/`uploads` 持久卷、启动自动迁移),配套 `.env.example`,一条
  `docker compose up -d --build` 上线。
- 性能索引迁移 `020_performance_indexes`:`resources` 两个复合索引
  (tenant+created_at DESC / tenant+type+created_at DESC)与两个 pg_trgm GIN 索引
  (title / abstract),对应 ORM 模型侧同名同形声明。

### Changed

- `TenantScopedMixin` 重构:统一租户列与索引声明,RLS 覆盖门(`test_rls_coverage`)
  保持全绿。

### Fixed

- Python 3.11 部署沙箱兼容:`app/core/db.py` 的 `paginate` 泛型从 PEP 695 语法改为
  等价 TypeVar 写法(3.12+ 行为不变)。
- CI 第三轮收尾:migrations job 的 `alembic check` 漂移(020 raw DDL 索引未在 ORM
  声明)→ 模型侧补齐 4 个同名同形索引;backend job lint 扩到 CI 全目录口径
  (`e2e_run_server.py` 的 import 后置属刻意设计,加 E402 per-file-ignores);
  precommit `fix end of files` 补 `.audit/W3-progress.md` 尾换行。

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

### Changed

- **README 三语版(EN / 简体中文 / 日本語)重做可视化与表述**:
  - `docs/assets/screenshots-overview.png` 换为**暗黑品牌风**总览图——深空底 +
    靛蓝紫、顶部「11 模块 / 644 测试 / 84% 覆盖率 / 66 E2E」数据条、末行品牌
    CTA 卡填满网格,`contact_sheet.py` 同步改版;
  - 新增**带说明的截图画廊**:按「阅读 / 发表 / 发现与运营」三段、每段 3 张关键
    页面,用 3 栏表格内联展示并配一句话说明,把最重要的页面直接可视化;
  - 修复 3 处死链:`ARCHITECTURE.md` / `DEPLOYMENT.md` 实际位于 `docs/`,补全路径;
    文档索引补上漏掉的 `SUPPORT.md`;
  - 日文版同步修正过期项:TypeScript 5.7 → 5.9、多租户标注「未实现」→ 已实现、
    路线图中已交付的多租户 / Passkey / DOI 由 `[ ]` 改为 `[x]`。

### Fixed

- 修复 CI 首跑 4 个 job 全红的四处问题,实现"推上去即全绿":
  - `backend` job 的版本校验脚本路径错误(步骤工作目录在 `apps/backend`,脚本在
    仓库根 `scripts/`),CI 报 127 找不到文件;
  - `migrations` job 未注入 `SCHOLARHUB_SECRET_KEY`:Settings 强校验拒绝缺失密钥,
    alembic 读配置时直接 ValidationError(CI 环境无 .env,已 gitignore);
  - frontend/e2e job 从 node 20 升到 node 22 并补 `engines: node>=22` 与 `.nvmrc`:
    依赖树里 jsdom@30 → undici@8 使用了 node 22+ 才有的 `webidl.util.markAsUncloneable`,
    node 20 下 vitest forks worker 全部启动失败(13 个测试文件 "no tests");
  - 修复推荐 fallback 的 E2E 断言:前端已把 `score === 0` 渲染为"最新收录",
    测试还在断言后端 reason 原文;用例改为自建前置资源,不再隐式依赖其他 spec
    的执行顺序(单跑该文件时目录可能为空)。
- CI 第二轮三处残余修复(run #1 后逐 job 转绿的收尾):
  - `engine.py` 补 `ruff format`(推荐 fallback 改动的遗留格式偏差,本地只跑过
    `ruff check` 没跑 format);
  - `migrations` job 密钥注入改用 `SCHOLARHUB_ENVIRONMENT=test`:非 test 环境
    强校验三件套(secret_key / admin_password / fernet_key),逐个硬编码会
    挤牙膏式暴露下一个缺失项,test 模式由配置层统一填充;
  - `e2e_run_server.py` 显式注入 `SCHOLARHUB_STORAGE_PATH=./storage`:默认值
    `/data/uploads` 在 CI runner(非 root)不可写,上传接口 500,
    "author can upload a PDF" 用例等不到 toast(本地靠 .env 掩盖)。
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

- 全库审查修复的配套测试：新增两条端到端用户旅程（`full-user-journey.spec.ts`——访客首屏
  → 注册 → 仪表盘统计 → 账号设置 → 目录筛选/多选；作者投稿 → 编辑分配 → 审稿人接单
  出报告 → 编辑接收 → 读者阅读并记住进度）；新增迁移 021 的存量 2FA 数据搬运回归
  （`test_migration_021_twofactor_carryover.py`，覆盖"老明文报名必须继续是 2FA 账号"）；
  新增 BibTeX 特殊字符转义回归；2FA 端到端用例改写到统一后的 `/api/auth/2fa/*`
  （恢复码 8→10、关闭需密码 + 验证码、关闭后旧会话按设计失效）。
- 已知遗留：`docs/assets/screenshots-overview.png` 顶部数据条里的 E2E 计数仍是 66（测试 644 / 覆盖率 84% 两项与当前一致）。`contact_sheet.py` 里的数字已改为 68，但重新生成图片需要带 Noto CJK 字体的环境（本轮开发机无该字体，未动二进制）。
- 删除 6 条随死代码（`doi.get_doi_metadata`）一起下线的用例。
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
