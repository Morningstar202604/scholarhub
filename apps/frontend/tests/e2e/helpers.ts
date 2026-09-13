import type { Page, Request } from '@playwright/test'

// E2E 测试共享的辅助函数。每个测试自己通过 UI 登录，避免依赖
// sessionStorage 持久化（zustand persist 的 partialize 只存 token，
// Playwright 的 storageState 不会自动捕获 sessionStorage）。

// 注意：example.org / example.com 是 RFC 2606 保留域名，但 email-validator
// 默认允许；.test / .example / .invalid / .localhost 会被它拒绝。
const E2E_DOMAIN = 'example.org'

export const ADMIN = {
  username: 'admin',
  password: 'e2e_admin_pw_12345678',
  email: 'admin@e2e.test',
} as const

export interface TestUser {
  email: string
  username: string
  password: string
}

// 用一个全局递增计数器避免多次运行重名冲突
let userCounter = 0
export function nextTestUser(prefix = 'e2e'): TestUser {
  userCounter += 1
  const stamp = `${Date.now().toString(36)}${userCounter}`
  return {
    email: `${prefix}.${stamp}@${E2E_DOMAIN}`,
    username: `${prefix}_${stamp}`.slice(0, 30),
    password: 'Passw0rd!e2e',
  }
}

// 通过 UI 登录。等待 toast.success('登录成功') 或路由跳转。
export async function loginViaUi(
  page: Page,
  creds: { username: string; password: string },
): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('用户名或邮箱').fill(creds.username)
  // exact:true 避免"确认密码"等带子串的 label 干扰（注册页就有两个密码框）
  await page.getByLabel('密码', { exact: true }).fill(creds.password)
  await page.getByRole('button', { name: '登录' }).click()
  // 等 dashboard 出现（admin 普通用户都会跳过去）
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

export async function logoutViaUi(page: Page): Promise<void> {
  // AppShell header 右侧的用户菜单触发按钮：唯一一个 aria-haspopup="menu" 的 button
  // （ThemeToggle 是普通 button，hamburger 是普通 button，登录/注册是 asChild 渲染成 <a>）。
  // 不用 force:true：Radix DropdownMenuTrigger 依赖 pointerdown 事件，actionability
  // 检查通过才能正确触发打开；force 会绕过部分事件派发。
  const trigger = page.locator('header button[aria-haspopup="menu"]').first()
  await trigger.waitFor({ state: 'visible', timeout: 10_000 })
  await trigger.click()
  // DropdownMenu 是 Radix，渲染 portal 后 menuitem 才出现；
  // waitFor visible 一下再点，避免 menuitem 异步挂载时 click 失败
  const item = page.getByRole('menuitem', { name: '退出登录' })
  await item.waitFor({ state: 'visible', timeout: 10_000 })
  await item.click()
  await page.waitForURL(/\/login/, { timeout: 10_000 })
}

interface OutboxEmail {
  to: string
  subject: string
  body: string
  html: string
}

// E2E 后端在 e2e_run_server.py 中注入了 dev-only /api/dev/email-outbox。
// 该接口返回最近 N 封内存邮件（不持久化、不污染 production）。
export async function fetchEmailOutbox(limit = 5): Promise<OutboxEmail[]> {
  const res = await fetch(
    `http://localhost:8000/api/dev/email-outbox?limit=${limit}`,
  )
  if (!res.ok) throw new Error(`outbox fetch failed: ${res.status}`)
  const json = (await res.json()) as { emails: OutboxEmail[] }
  return json.emails
}

export async function resetEmailOutbox(): Promise<void> {
  await fetch('http://localhost:8000/api/dev/email-outbox/reset', {
    method: 'POST',
  }).catch(() => {})
}

// 从邮件正文里提取验证 token，对应 verify-email 路由的 ?token=... 参数。
export function extractVerifyToken(body: string): string | null {
  const m = body.match(/token=([A-Za-z0-9._-]+)/)
  return m ? m[1] : null
}

// 通过 backend dev-only 接口直接置 is_email_verified=true。
// 用于"绕过邮件链接点击"的场景：比如我们只想测登录后的体验，
// 不必每次都走完整的"注册→邮件→点链接"流程。
export async function forceVerifyEmail(email: string): Promise<void> {
  await fetch('http://localhost:8000/api/dev/verify-email-by-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
}

// 通过 UI 走完整的注册→邮件→验证流程，返回已验证的用户凭据。
export async function registerAndVerifyViaUi(
  page: Page,
  user: TestUser,
): Promise<void> {
  await resetEmailOutbox()
  await page.goto('/register')
  await page.getByLabel('邮箱').fill(user.email)
  await page.getByLabel('用户名').fill(user.username)
  await page.getByLabel('密码', { exact: true }).fill(user.password)
  await page.getByLabel('确认密码').fill(user.password)
  await page.getByRole('button', { name: '注册' }).click()
  // 注册成功后 toast 显示 "注册成功，请查收邮件完成验证"，跳 /verify-email?email=...
  await page.waitForURL(/\/verify-email/, { timeout: 10_000 })

  // 抓邮件取 token
  const emails = await fetchEmailOutbox(3)
  const mine = emails.find((e) => e.to === user.email)
  if (!mine) throw new Error(`no email captured for ${user.email}`)
  const token = extractVerifyToken(mine.body)
  if (!token) throw new Error(`no token in email body:\n${mine.body}`)

  // verify-email.tsx 会从 URL ?token=... 读取并自动填入 input
  await page.goto(`/verify-email?token=${token}`)
  // 等输入框被填充（page load + useState init）
  await page.waitForLoadState('networkidle')
  // 验证按钮 + 等成功 toast
  await page.getByRole('button', { name: '验证' }).click()
  await page
    .getByText('邮箱验证成功，请登录')
    .waitFor({ state: 'visible', timeout: 10_000 })
}

// 等待网络空闲（用于 SPA 跳转后等数据请求完成）
export async function waitForNetworkIdle(page: Page, timeout = 5_000): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout }).catch(() => {})
}

// 抓取指定 URL 模式的请求体（用于断言前端发了正确的 API 请求）
export function captureRequests(page: Page, urlPattern: RegExp): Request[] {
  const captured: Request[] = []
  page.on('request', (req) => {
    if (urlPattern.test(req.url())) captured.push(req)
  })
  return captured
}
