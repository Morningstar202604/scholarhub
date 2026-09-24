import { test, expect, type Page } from '@playwright/test'
import {
  ADMIN,
  nextTestUser,
  registerAndVerifyViaUi,
  loginViaUi,
  primeCookieConsent,
} from './helpers'

/**
 * 全流程用户旅程：按"一个真人会怎么用这个站"的顺序，把整条业务链走一遍。
 *
 * Journey 1（新访客 → 用户）：
 *   访客第一眼 → 公开目录可见 → 受限页被弹回登录 → 注册/验证邮箱 → 登录
 *   → 仪表盘统计都是真实数字（不是 "—"）→ 账号设置页 → 目录筛选/多选/翻页
 *
 * Journey 2（作者 → 编辑 → 审稿人 → 读者）：
 *   作者投稿（带下载链接）→ 编辑分配审稿人 → 审稿人接受 + 提交报告
 *   → 编辑决定接收 → 文章自动进公开目录 → 作者看到"已接收"并收到通知
 *   → 读者打开阅读页、记进度、刷新后进度还在
 */

// 仪表盘统计卡：整张卡是一个 Link，label 在 CardTitle 里。
// 断言"不是 —"就是在断言背后的接口真的通了（之前非编辑用户会 403）。
async function expectStatNotDash(page: Page, label: string): Promise<void> {
  const tile = page.locator('a').filter({ hasText: label }).first()
  await expect(tile).toBeVisible({ timeout: 10_000 })
  await expect(tile).not.toContainText('—')
}

test.describe('全流程用户旅程', () => {
  test('Journey 1: 访客第一眼 → 注册 → 仪表盘 → 设置 → 目录浏览', async ({
    browser,
  }) => {
    // --- 1) 访客第一眼：根路径是公开门面页（不弹登录），公开目录无需登录 ---
    const guestCtx = await browser.newContext()
    const guest = await guestCtx.newPage()
    await primeCookieConsent(guest)

    await guest.goto('/')
    await expect(guest).toHaveURL(/\/$/, { timeout: 10_000 })
    await expect(
      guest.getByRole('heading', { name: /开放学术出版/ }),
    ).toBeVisible()
    // 首页有两处「登录」（横幅 + 门面区），限定到横幅避免 strict 歧义
    await expect(
      guest.getByRole('banner').getByRole('link', { name: '登录' }),
    ).toBeVisible()
    await expect(
      guest.getByRole('banner').getByRole('link', { name: '注册' }),
    ).toBeVisible()

    // 公开目录：访客能看列表
    await guest.goto('/catalog')
    await expect(guest.getByRole('heading', { name: '资源目录' })).toBeVisible({
      timeout: 10_000,
    })

    // 受限页对访客一律弹回登录（包含新加守卫的 /settings）
    for (const path of ['/dashboard', '/settings', '/submissions']) {
      await guest.goto(path)
      await expect(guest).toHaveURL(/login/, { timeout: 10_000 })
    }
    await guestCtx.close()

    // --- 2) 注册 → 验证邮箱 → 登录 ---
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    const user = nextTestUser('journey')
    await registerAndVerifyViaUi(page, user)
    await loginViaUi(page, user)

    // --- 3) 仪表盘：统计卡必须显示真实数字 ---
    await expect(page.getByRole('heading', { name: '概览' })).toBeVisible()
    // 新用户：我的投稿 0、未读通知 0 —— 关键是都不能是 "—"
    await expectStatNotDash(page, '我的投稿')
    await expectStatNotDash(page, '未读通知')
    await expectStatNotDash(page, '资源总数')
    await expectStatNotDash(page, '阅读列表')

    // --- 4) 账号设置页：资料 + 2FA 区块 ---
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: '账号设置' })).toBeVisible()
    // 用户名同时出现在侧边栏用户菜单和设置卡片里，限定到主区域。
    await expect(page.getByRole('main').getByText(user.username)).toBeVisible()
    await expect(page.getByText('两步验证（2FA）')).toBeVisible()

    // --- 5) 目录：筛选 → 多选 → 改筛选后选择被清空 ---
    // 先播一行可识别的资源（新建资源是管理员操作，借 admin 会话来建），
    // 否则全新库里表格是空的，勾选 / 导出这条链路无从验证。
    const seedTitle = `E2E Journey Seed ${Date.now()}`
    const adminCtx = await browser.newContext()
    const adminPage = await adminCtx.newPage()
    await loginViaUi(adminPage, ADMIN)
    await adminPage.goto('/catalog/new')
    await adminPage.getByLabel('标题').fill(seedTitle)
    await adminPage.getByLabel('作者（逗号分隔）').fill('Journey Author')
    await adminPage.getByLabel('学科', { exact: true }).fill('economics')
    await adminPage
      .getByLabel('摘要', { exact: true })
      .fill('Seed record for the full journey spec.')
    await adminPage.getByRole('button', { name: '创建' }).click()
    await expect(adminPage).toHaveURL(/\/catalog\/\d+/, { timeout: 10_000 })
    await adminCtx.close()

    await page.goto('/catalog')
    await expect(page.getByRole('heading', { name: '资源目录' })).toBeVisible()
    // 筛选栏是「输入后按回车」提交（不随每次按键发请求）。
    await page.getByPlaceholder('标题/作者/摘要').fill('Journey Seed')
    await page.getByPlaceholder('标题/作者/摘要').press('Enter')
    const seedRow = page.locator('table tbody tr').filter({ hasText: seedTitle })
    await expect(seedRow).toBeVisible({ timeout: 10_000 })

    // 勾选本页全部
    await page.getByRole('checkbox', { name: '全选' }).check()
    await expect(page.getByText(/已选 \d+ 项/)).toBeVisible()

    // 改筛选（等价于翻页 / 换排序）：勾选必须被清空，否则「导出」会把用户
    // 看不见的记录也导出去。这里换成同样能命中该行的关键词——行仍在页面上，
    // 所以断言的是"筛选动作清空了选择"，而不是"表格空了所以没得选"。
    await page.getByPlaceholder('标题/作者/摘要').fill(seedTitle)
    await page.getByPlaceholder('标题/作者/摘要').press('Enter')
    await expect(page.getByText(/已选 \d+ 项/)).toBeHidden({ timeout: 5_000 })
    await expect(seedRow).toBeVisible()

    await ctx.close()
  })

  test('Journey 2: 作者投稿 → 编辑分配 → 审稿 → 接收 → 读者阅读', async ({
    browser,
  }) => {
    const title = `E2E Journey ${Date.now()}`

    // --- 1) 作者：注册 → 登录 → 投稿（带下载链接） ---
    const authorCtx = await browser.newContext()
    const author = nextTestUser('jauthor')
    const authorPage = await authorCtx.newPage()
    await registerAndVerifyViaUi(authorPage, author)
    await loginViaUi(authorPage, author)

    await authorPage.goto('/submissions')
    await expect(authorPage.getByRole('heading', { name: '我的提交' })).toBeVisible()
    await authorPage.getByRole('button', { name: /新建提交/ }).click()
    await expect(authorPage.getByRole('dialog', { name: '新建提交' })).toBeVisible()
    await authorPage.getByLabel('标题').fill(title)
    await authorPage.getByLabel('作者（逗号分隔）').fill('Journey Author')
    await authorPage.getByLabel('学科', { exact: true }).fill('computer science')
    await authorPage
      .getByLabel('摘要', { exact: true })
      .fill('End-to-end journey submission.')
    // 下载链接是重点：这条路径以前会因 AnyHttpUrl 直塞 String 列而 500
    await authorPage
      .getByLabel('下载链接')
      .fill('https://arxiv.org/pdf/2401.00001')
    await authorPage.getByRole('button', { name: '提交' }).click({ force: true })
    await expect(authorPage.getByText('提交成功，等待审核')).toBeVisible({
      timeout: 10_000,
    })
    await expect(authorPage.getByText(title)).toBeVisible()

    // 仪表盘"我的投稿"应该变成 1（而不是永远 "—"）
    await authorPage.goto('/dashboard')
    const mineTile = authorPage.locator('a').filter({ hasText: '我的投稿' }).first()
    await expect(mineTile).toContainText('1', { timeout: 10_000 })

    // --- 2) 编辑：分配审稿人（自己） ---
    const adminCtx = await browser.newContext()
    const adminPage = await adminCtx.newPage()
    await loginViaUi(adminPage, ADMIN)
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByRole('heading', { name: '编辑工作台' })).toBeVisible()
    await expect(adminPage.getByText(title)).toBeVisible({ timeout: 10_000 })

    await adminPage.getByRole('button', { name: '分配审稿人' }).first().click()
    await expect(adminPage.getByText(/分配审稿人/).first()).toBeVisible()
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: /admin/ }).first().click()
    await adminPage.getByRole('button', { name: '确认分配' }).click()
    await expect(adminPage.getByText('已分配审稿人')).toBeVisible({ timeout: 5_000 })

    // --- 3) 审稿人：接受邀请 → 提交报告 ---
    await adminPage.goto('/review/assignments')
    await expect(adminPage.getByRole('heading', { name: '审稿工作台' })).toBeVisible()
    await expect(adminPage.getByText(title)).toBeVisible({ timeout: 10_000 })
    await adminPage.getByRole('button', { name: /接受邀请/ }).click()
    await expect(adminPage.getByText('已接受审稿邀请')).toBeVisible({ timeout: 5_000 })

    await adminPage.getByRole('button', { name: /填写审稿报告/ }).click()
    await expect(
      adminPage.getByRole('heading', { name: '填写审稿报告' }),
    ).toBeVisible()
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: '接收（Accept）' }).click()
    await adminPage.getByLabel('给作者的意见').fill('Solid work. Recommend accept.')
    await adminPage.getByRole('button', { name: '提交审稿报告' }).click()
    await expect(adminPage.getByText('审稿报告已提交')).toBeVisible({ timeout: 5_000 })

    // --- 4) 编辑：做决定 = 接收 ---
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByText(title)).toBeVisible()
    await adminPage.getByRole('button', { name: /做决定/ }).first().click()
    await expect(adminPage.getByText(/做决定/).first()).toBeVisible()
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: '接收（Accept）' }).click()
    await adminPage
      .getByLabel('编辑备注（作者可见）')
      .fill('Accepted based on reviewer report.')
    await adminPage.getByRole('button', { name: '确认决定' }).click()
    await expect(adminPage.getByText('决定已记录')).toBeVisible({ timeout: 5_000 })

    // --- 5) 作者：状态变"已接收"，并且收到通知 ---
    await authorPage.goto('/submissions')
    await expect(authorPage.getByText(title)).toBeVisible()
    await expect(authorPage.getByText('已接收').first()).toBeVisible({ timeout: 10_000 })

    await authorPage.goto('/notifications')
    // 决策会 fan-out 一条通知给作者；标题里带 "E2E Journey"
    await expect(authorPage.getByText(new RegExp(title.slice(0, 20)))).toBeVisible({
      timeout: 10_000,
    })

    // --- 6) 读者：公开目录里能搜到 → 打开阅读页 → 记进度 → 刷新后仍在 ---
    const readerCtx = await browser.newContext()
    const reader = nextTestUser('jreader')
    const readerPage = await readerCtx.newPage()
    await registerAndVerifyViaUi(readerPage, reader)
    await loginViaUi(readerPage, reader)

    await readerPage.goto('/catalog')
    await readerPage.getByPlaceholder('标题/作者/摘要').first().fill(title)
    await readerPage.getByPlaceholder('标题/作者/摘要').first().press('Enter')
    const link = readerPage.getByRole('link', { name: title })
    await expect(link).toBeVisible({ timeout: 10_000 })
    await link.click()
    await expect(readerPage).toHaveURL(/\/catalog\/\d+/, { timeout: 10_000 })
    const resourceId = Number(readerPage.url().match(/\/catalog\/(\d+)/)![1])

    await readerPage.goto(`/reader/${resourceId}`)
    await expect(readerPage.getByText(title).first()).toBeVisible({ timeout: 10_000 })
    await expect(readerPage.getByLabel('页码')).toHaveValue('1')
    await readerPage.getByLabel('页码').fill('4')
    await readerPage.getByLabel(/进度：/).fill('30')
    await readerPage.getByRole('button', { name: '保存进度' }).click()
    await expect(readerPage.getByText('进度已保存')).toBeVisible({ timeout: 5_000 })

    // 刷新：进度来自服务端而不是本地 state
    await readerPage.reload()
    await expect(readerPage.getByLabel('页码')).toHaveValue('4', { timeout: 10_000 })
    expect(Number(await readerPage.getByLabel(/进度：/).inputValue())).toBe(30)

    await authorCtx.close()
    await adminCtx.close()
    await readerCtx.close()
  })
})
