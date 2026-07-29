import { test as base, expect, type ConsoleMessage, type Page } from '@playwright/test'
import { ADMIN, loginViaUi } from './helpers'

// ─────────────────────────────────────────────────────────────────────────────
// 移动端专用 E2E（iPhone 13 视口，390×844）。
//
// 设计目标：验证"移动端是独立外壳，而非桌面端的响应式裁剪"：
//   - 底部 Tab 栏（概览/目录/通知/我的）可见；桌面侧边栏 + 汉堡按钮根本不渲染
//   - "我的"打开底部抽屉（而非侧边栏抽屉）
//   - 目录在移动端呈卡片流（role=table 不渲染），且卡片→详情→阅读 的链路在移动底部栏完成
//   - 登录后中心 FAB 跳 /ingest；仪表盘是 2 列大块 + 快捷操作（非桌面 5 列小卡）
//   - 全程无 console error
// ─────────────────────────────────────────────────────────────────────────────

// 每个测试独立监听 console error，结束后断言无"有意义"的报错。
// （过滤掉 favicon 404、静态资源 404 等与本功能无关的噪声。）
const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = []
    const onConsole = (msg: ConsoleMessage) => {
      if (msg.type() === 'error') errors.push(msg.text())
    }
    const onPageError = (err: Error) => errors.push(`pageerror: ${err.message}`)
    page.on('console', onConsole)
    page.on('pageerror', onPageError)
    // eslint-disable-next-line react-hooks/rules-of-hooks -- Playwright fixture 约定用 use() 注入，非 React Hook
    await use(errors)
    const meaningful = errors.filter(
      (e) => !/favicon|Failed to load resource|net::ERR|404 \(Not Found\)/i.test(e),
    )
    expect(meaningful, `移动端 console error: ${meaningful.join(' | ')}`).toEqual([])
  },
})

// 桌面壳层未渲染的移动端判定：汉堡按钮 + 侧边栏链接都不在 DOM 中。
async function expectDesktopShellAbsent(page: Page) {
  await expect(page.getByRole('button', { name: '打开菜单' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '资源目录', exact: true })).toHaveCount(0)
}

// 以 admin 在 UI 上建一条资源，保证目录有数据可测移动卡片。
async function createResourceViaUi(page: Page, title: string) {
  await page.goto('/catalog/new')
  await page.getByLabel('标题').fill(title)
  await page.getByLabel('作者（逗号分隔）').fill('Mobile Author')
  await page.getByLabel('学科', { exact: true }).fill('computer science')
  await page.getByLabel('摘要', { exact: true }).fill('Mobile e2e abstract.')
  await page.getByRole('button', { name: '创建' }).click()
  await expect(page).toHaveURL(/\/catalog\/\d+/, { timeout: 10_000 })
}

test.describe('mobile shell · 访客', () => {
  test('公开目录：底部 Tab 栏可见，桌面侧边栏/汉堡不渲染', async ({ page, consoleErrors }) => {
    void consoleErrors
    await page.goto('/catalog')
    await expect(page).toHaveURL(/\/catalog$/)

    // 移动底部 Tab 栏存在
    await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible()
    await expect(page.getByRole('button', { name: '概览' })).toBeVisible()
    await expect(page.getByRole('button', { name: '目录' })).toBeVisible()
    await expect(page.getByRole('button', { name: '通知' })).toBeVisible()
    await expect(page.getByRole('button', { name: '我的' })).toBeVisible()

    // 桌面壳层未渲染
    await expectDesktopShellAbsent(page)
  })

  test('"我的"打开底部抽屉（访客看到登录/注册入口）', async ({ page, consoleErrors }) => {
    void consoleErrors
    await page.goto('/catalog')
    await page.getByRole('button', { name: '我的' }).click()

    const sheet = page.getByRole('dialog', { name: '更多' })
    await expect(sheet).toBeVisible()
    await expect(sheet.getByRole('link', { name: '登录' })).toBeVisible()
    await expect(sheet.getByRole('link', { name: '注册' })).toBeVisible()

    // 抽屉内登录入口可跳转（验证抽屉内容真实可用）
    await sheet.getByRole('link', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('mobile shell · 已登录', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUi(page, ADMIN)
  })

  test('中心 FAB 可见并跳转到 /ingest', async ({ page, consoleErrors }) => {
    void consoleErrors
    await page.goto('/dashboard')
    const fab = page.getByRole('button', { name: '导入' })
    await expect(fab).toBeVisible()
    await fab.click()
    await expect(page).toHaveURL(/\/ingest/)
    await expectDesktopShellAbsent(page)
  })

  test('仪表盘呈移动 2 列大块 + 快捷操作（非桌面 5 列小卡）', async ({ page, consoleErrors }) => {
    void consoleErrors
    await page.goto('/dashboard')
    // 移动大块标签
    await expect(page.getByText('资源总数')).toBeVisible()
    await expect(page.getByText('我的推荐')).toBeVisible()
    // 快捷操作（3 列按钮）：与统计块同屏，需限定到快捷操作容器避免歧义
    const quick = page.getByTestId('mobile-quick-actions')
    await expect(quick.getByRole('link', { name: '浏览目录' })).toBeVisible()
    await expect(quick.getByRole('link', { name: '我的提交' })).toBeVisible()
    await expect(quick.getByRole('link', { name: '推荐' })).toBeVisible()
    // 桌面侧边栏不应出现
    await expectDesktopShellAbsent(page)
  })

  test('目录呈卡片（非表格），卡片→详情底部操作栏→阅读页底部操作栏', async ({
    page,
    consoleErrors,
  }) => {
    void consoleErrors
    const title = `E2E Mobile ${Date.now()}`
    await createResourceViaUi(page, title)

    // 回目录（移动卡片流）
    await page.goto('/catalog')
    await expect(page.getByRole('heading', { name: '资源目录' })).toBeVisible()
    // 关键：移动端用卡片，桌面表格不应渲染
    await expect(page.getByRole('table')).toHaveCount(0)
    const card = page.getByRole('link', { name: title })
    await expect(card).toBeVisible()

    // 卡片 → 详情页
    await card.click()
    await expect(page).toHaveURL(/\/catalog\/\d+/)
    // 移动详情底部操作栏
    await expect(page.getByRole('link', { name: '在线阅读' })).toBeVisible()
    await expect(page.getByRole('button', { name: '更多操作' })).toBeVisible()

    // 在线阅读 → 阅读页
    await page.getByRole('link', { name: '在线阅读' }).click()
    await expect(page).toHaveURL(/\/reader\/\d+/)
    // 阅读页移动底部栏（toolbar）：翻页 + 保存进度，与桌面侧栏控件互不重复
    const readerBar = page.getByRole('toolbar', { name: '阅读操作栏' })
    await expect(readerBar).toBeVisible()
    await expect(readerBar.getByRole('button', { name: '上一页' })).toBeVisible()
    await expect(readerBar.getByRole('button', { name: '下一页' })).toBeVisible()
    await expect(readerBar.getByRole('button', { name: '保存进度' })).toBeVisible()

    // 全程桌面壳层未渲染
    await expectDesktopShellAbsent(page)
  })
})
