import { test, expect } from '@playwright/test'
import {
  ADMIN,
  nextTestUser,
  registerAndVerifyViaUi,
  loginViaUi,
} from './helpers'

// 投稿 + 审稿完整流程(模仿用户点击)。
//
// 流程:
// 1) 作者注册并验证邮箱
// 2) 作者登录,在 /submissions 新建一条提交(pending)
// 3) admin(同时是 editor + reviewer) 在 /submissions/pending 看到提交
// 4) admin 分配审稿人(选自己)
// 5) admin 在 /review/assignments 看到 assignment,接受邀请,填审稿报告
// 6) admin 回 /submissions/pending 做决定 = accept,触发自动入 catalog
// 7) 作者回到 /submissions 看到状态变 accepted

test.describe('submissions + review flow', () => {
  const submittedTitle = `E2E Sub ${Date.now()}`

  test('full submission → review → accept cycle', async ({ browser }) => {
    // --- 1) 作者注册 + 验证邮箱 + 登录 + 投稿 ---
    const authorCtx = await browser.newContext()
    const author = nextTestUser('author')
    const authorPage = await authorCtx.newPage()
    await registerAndVerifyViaUi(authorPage, author)
    await loginViaUi(authorPage, author)

    await authorPage.goto('/submissions')
    await expect(authorPage.getByRole('heading', { name: '我的提交' })).toBeVisible()

    // 新建提交
    await authorPage.getByRole('button', { name: /新建提交/ }).click()
    await expect(authorPage.getByRole('dialog')).toBeVisible()
    await authorPage.getByLabel('标题').fill(submittedTitle)
    await authorPage.getByLabel('作者（逗号分隔）').fill('Auth One, Auth Two')
    await authorPage.getByLabel('学科', { exact: true }).fill('computer science')
    await authorPage.getByLabel('摘要', { exact: true }).fill('Submission abstract for E2E review flow.')
    await authorPage.getByRole('button', { name: '提交' }).click({ force: true })
    await expect(authorPage.getByText('提交成功，等待审核')).toBeVisible({ timeout: 5_000 })
    // 列表显示新提交
    await expect(authorPage.getByText(submittedTitle)).toBeVisible()

    // --- 2) admin 看到这条 pending 提交,分配审稿人 ---
    const adminCtx = await browser.newContext()
    const adminPage = await adminCtx.newPage()
    await loginViaUi(adminPage, ADMIN)
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByRole('heading', { name: '编辑工作台' })).toBeVisible()
    await expect(adminPage.getByText(submittedTitle)).toBeVisible({ timeout: 10_000 })

    // 分配审稿人
    await adminPage.getByRole('button', { name: '分配审稿人' }).first().click()
    await expect(adminPage.getByText(/分配审稿人/).first()).toBeVisible()
    // 选 admin 自己作为 reviewer
    await adminPage.locator('button[role="combobox"]').first().click()
    // admin 用户名出现在选项里
    await adminPage.getByRole('option', { name: /admin/ }).first().click()
    await adminPage.getByRole('button', { name: '确认分配' }).click()
    await expect(adminPage.getByText('已分配审稿人')).toBeVisible({ timeout: 5_000 })

    // --- 3) admin 在 /review/assignments 看到 assignment,接受 ---
    await adminPage.goto('/review/assignments')
    await expect(adminPage.getByRole('heading', { name: '审稿工作台' })).toBeVisible()
    await expect(adminPage.getByText(submittedTitle)).toBeVisible({ timeout: 10_000 })
    // 接受邀请
    await adminPage.getByRole('button', { name: /接受邀请/ }).click()
    await expect(adminPage.getByText('已接受审稿邀请')).toBeVisible({ timeout: 5_000 })

    // --- 4) 填审稿报告 ---
    await adminPage.getByRole('button', { name: /填写审稿报告/ }).click()
    // "填写审稿报告" 在 assignments.tsx 出现 3 处（PageHeader description、Button、DialogTitle）。
    // 用 heading role 精确匹配 DialogTitle（h2），避免 strict mode violation。
    await expect(adminPage.getByRole('heading', { name: '填写审稿报告' })).toBeVisible()
    // 改推荐决定
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: '接收（Accept）' }).click()
    // 给作者意见
    await adminPage.getByLabel('给作者的意见').fill('Looks good. Recommend accept.')
    // 提交
    await adminPage.getByRole('button', { name: '提交审稿报告' }).click()
    await expect(adminPage.getByText('审稿报告已提交')).toBeVisible({ timeout: 5_000 })

    // --- 5) admin 回 /submissions/pending 做决定 = accept ---
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByText(submittedTitle)).toBeVisible()
    await adminPage.getByRole('button', { name: /做决定/ }).first().click()
    await expect(adminPage.getByText(/做决定/).first()).toBeVisible()
    // 选 accept
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: '接收（Accept）' }).click()
    await adminPage.getByLabel('编辑备注（作者可见）').fill('Accepted based on reviewer report.')
    await adminPage.getByRole('button', { name: '确认决定' }).click()
    await expect(adminPage.getByText('决定已记录')).toBeVisible({ timeout: 5_000 })

    // --- 6) 作者回到 /submissions 看到状态变 accepted ---
    await authorPage.goto('/submissions')
    await expect(authorPage.getByText(submittedTitle)).toBeVisible()
    // 状态 badge 显示"已接收"
    await expect(authorPage.getByText('已接收').first()).toBeVisible({ timeout: 10_000 })

    // --- 7) 作者点开详情,看到审核备注 ---
    await authorPage.getByText(submittedTitle).click()
    await expect(authorPage.getByText('Accepted based on reviewer report.')).toBeVisible()

    // --- 8) accepted 的 submission 自动入 catalog,公开可见 ---
    const guestCtx = await browser.newContext()
    const guestPage = await guestCtx.newPage()
    await guestPage.goto('/catalog')
    // 用 link role 精确匹配：catalog 卡片同时把 title 渲染成 link 和 description paragraph，
    // getByText 会 strict-mode 报错（2 elements）。
    await expect(guestPage.getByRole('link', { name: submittedTitle })).toBeVisible({ timeout: 10_000 })

    await authorCtx.close()
    await adminCtx.close()
    await guestCtx.close()
  })

  test('author can cancel a pending submission', async ({ browser }) => {
    const authorCtx = await browser.newContext()
    const author = nextTestUser('author2')
    const authorPage = await authorCtx.newPage()
    await registerAndVerifyViaUi(authorPage, author)
    await loginViaUi(authorPage, author)

    await authorPage.goto('/submissions')
    await authorPage.getByRole('button', { name: /新建提交/ }).click()
    const title = `E2E Cancel ${Date.now()}`
    await authorPage.getByLabel('标题').fill(title)
    await authorPage.getByLabel('作者（逗号分隔）').fill('Cancellable Author')
    await authorPage.getByLabel('学科', { exact: true }).fill('history')
    await authorPage.getByLabel('摘要', { exact: true }).fill('Will be cancelled.')
    await authorPage.getByRole('button', { name: '提交' }).click({ force: true })
    await expect(authorPage.getByText('提交成功，等待审核')).toBeVisible({ timeout: 5_000 })

    // 点撤销
    await authorPage.getByRole('button', { name: '撤销' }).click()
    // ConfirmDialog
    await authorPage.getByRole('button', { name: '撤销', exact: true }).click()
    await expect(authorPage.getByText('已撤销提交')).toBeVisible({ timeout: 5_000 })
    // 列表中应该消失
    await expect(authorPage.getByText(title)).toHaveCount(0)

    await authorCtx.close()
  })

  test('author can upload a PDF file to pending submission', async ({ browser }) => {
    const authorCtx = await browser.newContext()
    const author = nextTestUser('author3')
    const authorPage = await authorCtx.newPage()
    await registerAndVerifyViaUi(authorPage, author)
    await loginViaUi(authorPage, author)

    await authorPage.goto('/submissions')
    await authorPage.getByRole('button', { name: /新建提交/ }).click()
    const title = `E2E Upload ${Date.now()}`
    await authorPage.getByLabel('标题').fill(title)
    await authorPage.getByLabel('作者（逗号分隔）').fill('Upload Author')
    await authorPage.getByLabel('学科', { exact: true }).fill('linguistics')
    await authorPage.getByLabel('摘要', { exact: true }).fill('Will get a file.')
    await authorPage.getByRole('button', { name: '提交' }).click({ force: true })
    await expect(authorPage.getByText('提交成功，等待审核')).toBeVisible({ timeout: 5_000 })

    // 点开详情 dialog
    await authorPage.getByText(title).click()
    await expect(authorPage.getByText('稿件文件')).toBeVisible()

    // 上传一个 PDF(用 Playwright setInputFiles)
    const fileInput = authorPage.locator('input[type="file"]').first()
    await fileInput.setInputFiles({
      name: 'manuscript.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\n% test pdf\n%%EOF\n', 'utf8'),
    })
    // "文件已上传" 在 detail dialog 中既出现在 toast（"文件已上传"），
    // 又以"稿件文件" + Badge "已上传" 的形式拼接成 accessible text "稿件文件已上传"，
    // 被 getByText('文件已上传') 同时匹配。用 exact:true 只匹配 toast 的独立文本节点。
    await expect(authorPage.getByText('文件已上传', { exact: true })).toBeVisible({
      timeout: 5_000,
    })
    // Badge "已上传" 是 detail dialog 内独立节点，用 exact:true 精确匹配
    await expect(authorPage.getByText('已上传', { exact: true })).toBeVisible()

    await authorCtx.close()
  })

  test('revision → author edits manuscript → resubmit with note → version history', async ({
    browser,
  }) => {
    // Phase 2.4 全链路：大修 → 作者真正修改内容 → 带修改说明重投 →
    // 作者与编辑双方都能在版本历史里看到 v1/v2 与作者说明。
    const authorCtx = await browser.newContext()
    const author = nextTestUser('reviser')
    const authorPage = await authorCtx.newPage()
    await registerAndVerifyViaUi(authorPage, author)
    await loginViaUi(authorPage, author)

    // --- 1) 作者投稿 ---
    await authorPage.goto('/submissions')
    await authorPage.getByRole('button', { name: /新建提交/ }).click()
    const title = `E2E Revise ${Date.now()}`
    await authorPage.getByLabel('标题').fill(title)
    await authorPage.getByLabel('作者（逗号分隔）').fill('Revision Author')
    await authorPage.getByLabel('学科', { exact: true }).fill('economics')
    await authorPage.getByLabel('摘要', { exact: true }).fill('Original abstract v1.')
    await authorPage.getByRole('button', { name: '提交' }).click({ force: true })
    await expect(authorPage.getByText('提交成功，等待审核')).toBeVisible({
      timeout: 5_000,
    })

    // --- 2) admin 决定 = 大修 ---
    const adminCtx = await browser.newContext()
    const adminPage = await adminCtx.newPage()
    await loginViaUi(adminPage, ADMIN)
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByText(title)).toBeVisible({ timeout: 10_000 })
    // 编辑工作台是卡片布局（不是表格），用 data-testid 锚定到目标稿件那张卡片
    const card = adminPage.locator('[data-testid="submission-card"]', {
      hasText: title,
    })
    await card.getByRole('button', { name: /做决定/ }).click()
    await adminPage.locator('button[role="combobox"]').first().click()
    await adminPage.getByRole('option', { name: /大修/ }).click()
    await adminPage
      .getByLabel('编辑备注（作者可见）')
      .fill('Please expand the methodology.')
    await adminPage.getByRole('button', { name: '确认决定' }).click()
    await expect(adminPage.getByText('决定已记录')).toBeVisible({ timeout: 5_000 })

    // --- 3) 作者看到大修，修改稿件内容（这是 2.4 之前根本做不到的事）---
    await authorPage.goto('/submissions')
    await expect(authorPage.getByText('大修').first()).toBeVisible({
      timeout: 10_000,
    })
    await authorPage.getByText(title).click()
    await authorPage.getByRole('button', { name: '修改稿件' }).click()
    await expect(authorPage.getByRole('heading', { name: '修改稿件' })).toBeVisible()
    // 表单已回填原值；只改摘要
    await authorPage
      .getByLabel('摘要', { exact: true })
      .fill('Revised abstract v2 with expanded methodology.')
    await authorPage.getByRole('button', { name: '保存修改' }).click({ force: true })
    await expect(authorPage.getByText('稿件已更新')).toBeVisible({ timeout: 5_000 })

    // --- 4) 带修改说明重投 ---
    await authorPage.getByRole('button', { name: '重投提交' }).click()
    await authorPage.getByLabel('修改说明（可选）').fill('已按意见扩写方法论一节')
    await authorPage.getByTestId('confirm-resubmit').click()
    await expect(authorPage.getByText('已重投，等待编辑再次审核')).toBeVisible({
      timeout: 5_000,
    })

    // --- 5) 作者详情里能看到 v1 + v2 版本历史与修改说明 ---
    await expect(authorPage.getByText('版本历史')).toBeVisible({ timeout: 5_000 })
    await expect(authorPage.getByText('v2', { exact: true })).toBeVisible()
    await expect(authorPage.getByText(/已按意见扩写方法论一节/)).toBeVisible()

    // --- 6) 编辑侧详情也能看到版本历史 + 改过的内容 ---
    await adminPage.goto('/submissions/pending')
    await expect(adminPage.getByText(title)).toBeVisible({ timeout: 10_000 })
    await adminPage
      .locator('[data-testid="submission-card"]', { hasText: title })
      .getByRole('button', { name: '详情' })
      .click()
    // 断言限定在详情 dialog 内：改后的摘要同时出现在列表卡片摘要里，
    // 页面级 getByText 会 strict-mode 命中 2 个节点。
    const detailDialog = adminPage.getByRole('dialog')
    await expect(detailDialog.getByText('版本历史')).toBeVisible({ timeout: 5_000 })
    await expect(detailDialog.getByText('v2', { exact: true })).toBeVisible()
    await expect(detailDialog.getByText(/已按意见扩写方法论一节/)).toBeVisible()
    await expect(
      detailDialog.getByText(/Revised abstract v2 with expanded methodology/),
    ).toBeVisible()

    await authorCtx.close()
    await adminCtx.close()
  })
})
