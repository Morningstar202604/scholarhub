# ScholarHUB W3 审查作战图（主理人汇编）

> 预设：W3 加固既有代码（Phase 5 安全+性能、Phase 6 代码质量+无障碍，不动架构）。
> 范围：`apps/backend/app` + `apps/frontend/src` + `alembic/versions` + `infra`。
> 说明：性能专家产出完整；安全/代码质量/无障碍三路因 429/502 限流未由 worker 完成，主理人已亲自读源补完（见文末"编排复盘"）。

---

## 一、安全（security）

### 可信的声明（验证通过）
| 声明 | 证据 | 判定 |
|---|---|---|
| JWT 密钥轮换零中断 | `core/key_rotation.py:107-153` 当前 key 签名、前序 key 仅验证，type 错配不回退（L148-151） | ✅ 落地 |
| refresh cookie HttpOnly+Secure+SameSite | `api/auth.py:82-92` `httponly=True, secure, samesite`（默认 strict，`core/config.py refresh_token_cookie_samesite="strict"`） | ✅ |
| 防枚举 | `api/auth.py:69-73, 514-532` 重复注册/密码找回返回统一文案 | ✅ |
| 租户隔离（RLS 第二层） | 各模块迁移分散建 `ENABLE+FORCE ROW LEVEL SECURITY` + `tenant_isolation` policy（002/003/004/005/006/007/009/011/012）；`FORCE` 连表 owner 也受限；`SET LOCAL app.current_tenant_id` 事务级 | ✅ 双层真实存在 |
| 限流 fail-open 不放大攻击 | `middleware/rate_limit.py:111-123` trust-XFF；`core/rate_limit_store.py:89-94` 被拒请求不进 bucket（防 DoS 自延长）；`STRICT_PATHS` 2FA 10/分 vs 100 万组合 | ✅ |
| 存储路径穿越 | `core/storage.py:52-58` `_validate_key` 拒绝对路径/`..` 段 | ✅ |
| 上传/PDF 同源 XSS 防护 | 前端 `reader/$resourceId.tsx:23-30` `isSafeDownloadUrl` 仅放行 https；iframe `sandbox="allow-same-origin allow-popups"` + title（L213-218） | ✅ 前端 |
| 2FA pending token 防重放 | `core/security.py:91-127` 5min 短 TTL + 仅 `2fa_pending` 类型 | ✅ |

### Finding（按严重度）
**S-1【Medium】两套 TOTP 实现并存，按场景分裂**
- `api/two_factor.py:37` 走 `core/totp.py`（手写 80 行，理由"pyotp 在 deny list"）做 2FA 启用；`api/auth.py:51` / `api/users.py:22` 走 `core/twofactor.py`（pyotp）的 `verify_totp_code` 做登录/改密验证。
- 风险：两套验证器若行为漂移（窗口/密钥编码/base32 padding），会出现"启用成功但登录验不过"的诡异 bug；改 TOTP 算法容易只改一套。
- 建议：统一到一套验证器，代价低（合并 ~30 行）。

**S-2【Medium】RLS 仅生产 PostgreSQL 生效，SQLite（dev/CI/E2E）零覆盖**
- 各模块 RLS 是 PG 方言 `op.execute`；SQLite 测试跳过（ARCHITECTURE 已声明）。所有租户隔离测试实际只验证应用层 `tenant_id == ...` 过滤，RLS 第二层在 CI 从不触发。
- 建议：保留但 CI 注释明示"RLS 未在 CI 验证"，`test_rls_isolation.py` 标注 PG-only + 可选 CI matrix。

**S-3【Low】`001` 审计表 policy 的 `WITH CHECK` 允许 `tenant_id IS NULL` 写入**
- `001_initial_schema_with_rls.py:74-77`。若代码写 audit 漏填 tenant_id，NULL 行绕过租户归属。建议 service 层断言非空。

**S-4【Low】依赖 CVE 未逐项核实（额度限制）**
- 本地未跑 `uv lock --check`/`pip-audit`。标记 `[待核实: 依赖 CVE 扫描结果]`，建议 CI 加 `pip-audit`/`npm audit` 例行门。

### 安全总体判断
"默认安全"声明**大部分可信且落地扎实**（密钥轮换、双层 RLS、anti-enumeration、限流 fail-open、存储穿越、PDF 协议白名单都经得起逐行看）。主要风险集中在 **TOTP 双实现（S-1）** 和 **RLS 测试面盲区（S-2）**——都是可维护性引发的安全债，不是恶意或疏忽漏洞。

---

## 二、性能（performance，专家完整产出）
9 项 finding（会话内金性能产出），三大债：
- **F1 最高**：`recommendations/engine.py:173-184` 把整个未读目录物化进 Python 内存（含 abstract/JSON），无列裁剪/封顶/缓存 → 单请求 1-3s + 内存尖峰。
- **F2+F3+F4 三连**：`catalog/routes.py:174-184` 全表 tags 扫描 + `resources` 缺 `(tenant_id,created_at)` 等复合索引 + ILIKE 前导通配 seq scan + 无读缓存层 → 匿名浏览 = seq scan + 全排序 + 全表 tags + 直击 DB。
- **F7**：`playwright.config.ts` `workers:1, fullyParallel:false`，66 E2E 单 worker 串行卡 CI（4-10+ 分钟墙钟）。
- 修正点：N+1 实为**数据量型**（F1/F2），非 ORM 懒加载型；library/submission/review 已用 `selectinload`。

---

## 三、代码质量与可维护性

**Q-1【High】core/ 过度膨胀 + 两套 TOTP 文件**
- `core/` 塞了 20+ 文件（captcha、key_rotation、orcid、search、storage、email、retention、twofactor、totp...），远超"身份/租户/角色/模块注册表"边界；`totp.py` 与 `twofactor.py` 功能重叠（见 S-1）。
- 建议：core 收敛，storage/email/orcid/search/retention 下沉为独立 service 或模块；TOTP 合并为单一实现。

**Q-2【Medium】模块 RLS 分散在 9 个迁移里，新增表易漏建 policy**
- 各模块表 RLS 随模块迁移各自 `op.execute`（catalog 在 002、doi 在 019...），无统一约束。新增表若忘记在模块迁移补 `ENABLE+FORCE+CREATE POLICY`，失去 RLS 第二层。
- 建议：CI 加检查（lint 每个含 `tenant_id` 的模型必须有对应 RLS policy 迁移）或集中 `rls_manifest` 启动校验。

**Q-3【Medium】疑似死代码待清理**
- `core/token_denylist.py` vs `core/tokens.py`（stateless verify/reset）职责相近需确认是否重复；`core/webauthn.py`(12981B) 与 `api/webauthn.py` 两层分工需确认。标记 `[待核实: 死代码 grep 确认]`。

**Q-4【Low】模块 models/schemas 大量复制 `tenant_id` 字段样板**
- 每个模块重复声明 `tenant_id = Column(UUID, nullable=False, index=True)`，建议 Mixin 统一。

### 代码质量总体判断
架构契约（模块化、模块间不直接 import）执行不错；最大可维护性债是 **core 膨胀 + TOTP 双实现（Q-1/S-1）** 和 **RLS 分散导致新增表易漏 policy（Q-2）**。

---

## 四、无障碍（accessibility）

**A-1【Medium】PDF 阅读器控件缺 `aria-valuetext` 与可访问页码跳转**
- `reader/$resourceId.tsx:241-265` 页码 Input+上/下一页（桌面端有），iframe 内 PDF 翻页读屏无法精确导航（只给 iframe `title=data.title`，L215）；进度 range（L273-281）缺 `aria-valuetext`。
- 建议：range 加 `aria-valuetext={progressPercent+'%'}`；PDF 增加可访问的"当前页/总页数"文本（视觉隐藏 + aria-live）；需页内导航上 react-pdf。

**A-2【Low】状态徽章可能纯色彩区分**
- 各页 status/类型用 `<Badge>`（shadcn/ui），需抽查 variant 是否纯色彩区分（WCAG 1.4.1）。建议 status 徽章附文本。

**A-3【Info】加分项（做得好）**
- 移动端阅读工具栏 `role="toolbar" aria-label="阅读操作栏"`（L333-335）；shadcn/ui 普遍带 `focus-visible` 环 + `sr-only`；cookie-banner/error-boundary 用 `role=`。整体 a11y 基线高于"默认忽略"水平。

### 无障碍总体判断
基线扎实（focus-visible、sr-only、移动端 toolbar ARIA 都有）。债集中在 **PDF 阅读器读屏导航（A-1）**——该页最容易被 WCAG 审计挂的点。

---

## 五、修复优先级（跨环节汇总 Action List）
| 优先级 | 项 | 环节 | 一句话 |
|---|---|---|---|
| P0 | F1 | 性能 | recommendations 候选集列裁剪+封顶+短 TTL 缓存 |
| P0 | F3 | 性能 | resources 加 `(tenant_id,created_at DESC)` 复合索引 + title/abstract GIN trigram |
| P1 | F2/F4 | 性能 | catalog facets 改服务端 SQL 聚合；catalog 公开读加短 TTL Redis 缓存 |
| P1 | S-1/Q-1 | 安全+质量 | TOTP 合并单一实现，删 `twofactor.py` 重复部分 |
| P1 | A-1 | 无障碍 | 阅读器 range 加 aria-valuetext + 页码 aria-live |
| P2 | F7 | 性能 | E2E 多 worker + 每 worker 独立 DB |
| P2 | Q-2 | 质量 | RLS policy 加 CI 校验，防新增表漏建 |
| P2 | S-4 | 安全 | CI 加 pip-audit / npm audit |
| P3 | F5/F8/F9 | 性能 | 进度同步 `select(Resource.id)`；`useResources` staleTime 对齐 5min；PDF 服务端 Range |
| P3 | S-3/Q-3/Q-4 | 安全+质量 | audit 非空 tenant 断言；清死代码；tenant_id Mixin |

## 六、编排复盘（透明说明）
- 一开始并行 fan-out 4 个后台 agent，叠加触发**免费 API 限流（429）**，安全/代码质量/无障碍 3 路全挂（性能那路先完成、拿到产出）。
- 这是编排失误（并发过高），不是代码或专家问题。改串行后重试仍撞限流窗口，故主理人**亲自读源**补完安全/质量/无障碍三路（上文证据均为本人实读），避免再烧额度。
- 教训：4 个重后台 agent 并行会打爆免费额度；后续多专家审查应**串行**或**限并发 1-2**，每个 worker 控制 token 量。

---

## 七、修复落地记录（P0/P1 已完成 commit fcd9100，P2/P3 本批次）

### P0/P1（commit fcd9100，已验证 644 通过 / 前端 100 通过）
| 项 | 落地 | 证据 |
|---|---|---|
| F1 | `recommendations/engine.py` 候选集列裁剪 + 封顶 + 短 TTL | 模块测试通过 |
| F3 | `020_performance_indexes.py` 加 `(tenant_id,created_at DESC)` 复合索引 + title/abstract GIN trigram | 迁移通过 |
| S-1/Q-1 | 删 `security.py` 死 2FA token 函数；`two_factor.py` 重指 `twofactor.py` | 644 通过 |
| A-1 | 阅读器 range 加 `aria-valuetext` + 页码 `aria-live` | 前端 100 通过 |

### P2/P3（本批次，验证 646 通过 / 前端 100 + tsc 绿）
| 项 | 落地 | 关键改动 | 验证 |
|---|---|---|---|
| **F7** | E2E 多 worker + per-worker DB 分片 | `e2e_run_server.py` 参数化 `E2E_DB_PATH`/`E2E_PORT`；`helpers.ts` 改读 `E2E_BACKEND_URL`；`playwright.config.ts` `E2E_WORKERS` 驱动 `workers`/`fullyParallel`（默认 1 串行不变） | tsc 绿，默认行为不变 |
| **Q-2** | RLS policy CI 静态校验 | 新增 `tests/test_rls_coverage.py`（SQLite 可跑，每次 CI 触发）：解析每个迁移里 `create_table(tenant_id)` 必须配 RLS enable；`tenants` 白名单为 tenancy root；`tenant_hosts` 白名单为 intentional no-RLS（见 017 docstring） | 2 测试通过 |
| **Q-2 附带发现** | **真实 RLS 缺口修复** | detector 揪出 `015_discipline_ontology.py` 的 `disciplines`/`subdisciplines` 是 per-tenant 表但**漏建 RLS policy**（第二层隔离缺失）→ 已补 `ENABLE+FORCE+CREATE POLICY tenant_isolation`（与 002/004 同模式） | 迁移 015 测试通过 |
| **S-4** | 依赖 CVE CI 门 | `ci.yml` 加 `npm audit`（frontend job）；`pip-audit` 已存在（security job L187-193） | ci.yml 校验 |
| **F5** | reader 进度同步列裁剪 | `reader/routes.py` `record_view`/`get_progress`/`update_progress` 的 `select(Resource)` 全行物化改 `select(Resource.id)` + `scalar_one_or_none()` | 24 测试通过 |
| **F8** | `useResources` staleTime 对齐 | `use-modules.ts:143` 加 `staleTime: 5 * 60_000`（对齐 `useCatalogStats`/`useCatalogFacets`） | 前端 100 通过 |
| **S-3** | 审计 tenant 非空收口 + 写顺序修复 | ① `models/__init__.py` `AuditLog.__init__` 加 `tenant_id` 非空断言（`audit_tenant_exempt=True` 例外）；② `submission/routes.py` 3 处「commit 后才 add 审计」改「add 后同事务 commit」 | 646 通过 |
| **Q-3** | 死代码清理（结论=无项可删） | 勘误：`core/token_denylist`/`core/tokens`/`core/webauthn` 全部是活代码、职责各异（`_random_jti` 被 `encode_token` 内部调用，非死代码）。**零删除，仅备案** | 活代码 import 验证 |

### Q-3 勘误说明
原报告（第 63-64 行）标记 `token_denylist`/`tokens`/`webauthn` 为「疑似死代码待清理」。实读勘误：
- `core/token_denylist.py` — 被 `api/auth.py:38` import `get_denylist`，auth.py 实际调用 `is_denied`/`add`，两个测试文件引用 → **活代码**。
- `core/tokens.py` — 被 `api/auth.py:39-45`、`api/webauthn.py:28` import；`_random_jti()` 被 `encode_token` 内部 `"jti": _random_jti()` 调用 → **活代码**（非死代码）。
- `core/webauthn.py`（算法层）vs `api/webauthn.py`（路由层）— 职责清晰无重叠，`api/webauthn.py:29` import `core` 的 4 个公开函数 → **活代码**。
- **结论**：Q-3 无项可删，保留原状。

### 未在本批次（保留待评估）
| 项 | 原因 |
|---|---|
| F2/F4（catalog facets SQL 聚合 + 读缓存） | P1 级，需 SQL 聚合重构 + Redis 缓存层，爆炸半径大，建议单独批次 |
| F9（PDF 服务端 Range） | 依赖 PDF 服务架构，建议与 F2/F4 同批 |
| Q-4（tenant_id Mixin） | 纯重构，不修 bug，建议单独批次 |
| S-1/Q-1 的 TOTP 合并 | 已在 P0/P1 删除死代码部分，剩余 `totp.py` vs `twofactor.py` 合并属架构层，需专项 |
