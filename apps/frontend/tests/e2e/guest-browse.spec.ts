import { test, expect } from '@playwright/test'
import { ADMIN } from './helpers'

// 未登录访客的浏览体验。
// 校验:
// - 根路径 / 未登录时跳 /login
// - /catalog 未登录可访问（公开目录）
// - /catalog/$resourceId / /reader/* 未登录会被守卫挡回 /login
// - 顶部菜单对未登录用户显示「登录」「注册」按钮

test.describe('guest browse', () => {
  test('root redirects to /login when not authenticated', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login$/)
  })

  test('catalog is publicly visible without login', async ({ page }) => {
    await page.goto('/catalog')
    await expect(page).toHaveURL(/\/catalog$/)
    // 页面 header
    await expect(page.getByRole('heading', { name: '资源目录' })).toBeVisible()
    // 筛选 placeholder
    await expect(page.getByPlaceholder('标题/作者/摘要')).toBeVisible()
  })

  test('catalog detail requires login and bounces to /login', async ({ page }) => {
    await page.goto('/catalog/1')
    await expect(page).toHaveURL(/\/login/)
  })

  test('reader requires login and bounces to /login', async ({ page }) => {
    await page.goto('/reader/1')
    await expect(page).toHaveURL(/\/login/)
  })

  test('dashboard requires login and bounces to /login', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })

  test('library / follows / notifications / submissions / ingest / recommendations require login', async ({ page }) => {
    for (const path of [
      '/library',
      '/follows',
      '/notifications',
      '/submissions',
      '/ingest',
      '/recommendations',
      '/review/assignments',
    ] as const) {
      await page.goto(path)
      await expect(page, `${path} should bounce to /login`).toHaveURL(/\/login/)
    }
  })

  test('admin pages bounce to /login for guests', async ({ page }) => {
    await page.goto('/admin/users')
    await expect(page).toHaveURL(/\/login/)
    await page.goto('/admin/audit-logs')
    await expect(page).toHaveURL(/\/login/)
  })

  test('header shows 登录 + 注册 buttons when not logged in', async ({ page }) => {
    await page.goto('/catalog')
    await expect(page.getByRole('link', { name: '登录' }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: '注册' }).first()).toBeVisible()
  })

  test('login page renders email + password fields and submit button', async ({ page }) => {
    await page.goto('/login')
    // 登录页标题是 CardTitle（非 h1/h2），用 text 断言即可
    await expect(page.getByText('登录', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('使用账号密码登录 ScholarHUB。')).toBeVisible()
    await expect(page.getByLabel('用户名或邮箱')).toBeVisible()
    await expect(page.getByLabel('密码', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
    // 顶部 header + 卡片底部各有一个"注册"链接，取 first 即卡片里的那个
    await expect(page.getByRole('link', { name: '注册' }).first()).toBeVisible()
    await expect(page.getByRole('link', { name: '忘记密码？' })).toBeVisible()
  })

  test('login with wrong password shows error toast', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('用户名或邮箱').fill(ADMIN.username)
    await page.getByLabel('密码', { exact: true }).fill('totally-wrong-password')
    await page.getByRole('button', { name: '登录' }).click()
    // toast.error 出现（具体文案由 backend 决定，断言部分关键字）
    await expect(page.locator('[data-sonner-toast]')).toBeVisible({ timeout: 5_000 })
  })
})
