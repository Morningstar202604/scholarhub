import { test, expect } from '@playwright/test'
import { ADMIN } from './helpers'

// 未登录访客的浏览体验。
// 校验:
// - 根路径 / 未登录时跳 /login
// - /catalog 与 /catalog/$resourceId 未登录可访问（公开目录 + 公开详情）
// - 详情页对访客隐藏鉴权能力（阅读进度/关注），显示"登录后阅读全文"引导
// - /reader/* 未登录会被守卫挡回 /login
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

  test('catalog detail is publicly visible with login CTA for guests', async ({
    page,
    request,
  }) => {
    // 用 admin API 造一条资源（详情页需要真实数据；E2E 库启动时为空）
    const loginRes = await request.post('http://localhost:8000/api/auth/login', {
      data: { username: ADMIN.username, password: ADMIN.password },
    })
    expect(loginRes.ok()).toBeTruthy()
    const { access_token } = (await loginRes.json()) as { access_token: string }
    const createRes = await request.post('http://localhost:8000/api/catalog', {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        slug: `guest-detail-${Date.now().toString(36)}`,
        type: 'paper',
        title: '访客可见的公开论文',
        authors: ['Guest Author'],
        year: 2024,
        discipline: 'Computer Science',
        abstract: '这是一篇用于验证访客可以直接查看目录详情页的测试论文摘要。',
      },
    })
    expect(createRes.ok()).toBeTruthy()
    const { id } = (await createRes.json()) as { id: number }

    // 访客直接访问详情页：不再被挡回 /login
    await page.goto(`/catalog/${id}`)
    await expect(page).toHaveURL(new RegExp(`/catalog/${id}$`))
    await expect(
      page.getByRole('heading', { name: '访客可见的公开论文' }),
    ).toBeVisible()
    // 摘要/元数据可见（preview 会由后端从 abstract 自动填充，文本出现两次，取首个）
    await expect(
      page.getByText('这是一篇用于验证访客可以直接查看目录详情页').first(),
    ).toBeVisible()
    // 鉴权能力降级：显示登录引导，而非"在线阅读"
    await expect(
      page.getByRole('link', { name: '登录后阅读全文' }).first(),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: '在线阅读' })).toHaveCount(0)
    // 阅读进度卡 / 关注卡对访客隐藏
    await expect(page.getByText('阅读进度', { exact: true })).toHaveCount(0)
    await expect(page.getByText('关注', { exact: true })).toHaveCount(0)

    // 点击登录引导跳 /login
    await page.getByRole('link', { name: '登录后阅读全文' }).first().click()
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
