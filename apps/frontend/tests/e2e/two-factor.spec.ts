import { createHmac } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { nextTestUser, loginViaUi, registerAndVerifyViaUi } from './helpers'

/**
 * Phase 3.1 全链路：开启 2FA → 登出 → 密码登录被要求二次验证 →
 * 输入 TOTP 码完成登录 → 关闭 2FA 恢复一步登录。
 *
 * TOTP 码在 Node 侧用 crypto 直接算（RFC 6238 / SHA-1 / 30s 步长），
 * 与后端 pyotp 的默认参数完全一致，无需引入额外依赖。
 */

function base32Decode(input: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = 0
  let value = 0
  const bytes: number[] = []
  for (const ch of input.replace(/=+$/, '').toUpperCase()) {
    const idx = alphabet.indexOf(ch)
    if (idx === -1) continue
    value = (value << 5) | idx
    bits += 5
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff)
      bits -= 8
    }
  }
  return Buffer.from(bytes)
}

function totp(secret: string, timestamp = Date.now()): string {
  const counter = Math.floor(timestamp / 1000 / 30)
  const buf = Buffer.alloc(8)
  buf.writeBigUInt64BE(BigInt(counter))
  const hmac = createHmac('sha1', base32Decode(secret)).update(buf).digest()
  const offset = hmac[hmac.length - 1] & 0x0f
  const code =
    ((hmac[offset] & 0x7f) << 24) |
    (hmac[offset + 1] << 16) |
    (hmac[offset + 2] << 8) |
    hmac[offset + 3]
  return String(code % 1_000_000).padStart(6, '0')
}

test.describe('two-factor authentication', () => {
  test('enable 2FA → two-step login → disable restores plain login', async ({
    browser,
  }) => {
    const ctx = await browser.newContext()
    const user = nextTestUser('twofa')
    const page = await ctx.newPage()
    await registerAndVerifyViaUi(page, user)
    await loginViaUi(page, user)

    // --- 1) 账号安全页开启 2FA ---
    await page.goto('/account/security')
    await page.getByTestId('start-2fa-setup').click()
    // secret 以等宽文本展示在 QR 下方
    const secretEl = page.locator('p.font-mono')
    await expect(secretEl).toBeVisible({ timeout: 5_000 })
    const secret = (await secretEl.textContent())!.trim()
    expect(secret.length).toBeGreaterThanOrEqual(16)

    await page.getByLabel('验证码').fill(totp(secret))
    await page.getByTestId('confirm-enable-2fa').click()
    // 不断言 toast 文本：「两步验证已开启」与卡片标题+徽章的拼接文本
    // （"两步验证" + "已开启"）在 strict mode 下撞车。恢复码出现 = 启用成功。
    const codes = page.getByTestId('recovery-codes')
    await expect(codes).toBeVisible({ timeout: 5_000 })
    await expect(codes.locator('span')).toHaveCount(8)
    await page.getByRole('button', { name: '我已保存' }).click()

    // --- 2) 登出 → 重新登录进入两步验证 ---
    await page.goto('/login')
    // 直接清 storage 模拟登出（避免依赖 UI 菜单路径）
    await page.evaluate(() => localStorage.clear())
    await page.goto('/login')
    await page.getByLabel('用户名或邮箱').fill(user.username)
    await page.getByLabel('密码', { exact: true }).fill(user.password)
    await page.getByRole('button', { name: '登录', exact: true }).click()

    // CardTitle 渲染为 div（非 heading role），用精确文本定位
    await expect(page.getByText('两步验证', { exact: true })).toBeVisible({
      timeout: 5_000,
    })
    await expect(page.getByTestId('confirm-2fa')).toBeVisible()

    // 错误码先被拒绝
    await page.getByLabel('验证码').fill('000000')
    await page.getByTestId('confirm-2fa').click()
    await expect(page.getByText('验证码错误，请重试')).toBeVisible({
      timeout: 5_000,
    })

    // 正确 TOTP 完成登录
    await page.getByLabel('验证码').fill(totp(secret))
    await page.getByTestId('confirm-2fa').click()
    await expect(page.getByText('登录成功')).toBeVisible({ timeout: 5_000 })
    await expect(page).toHaveURL(/dashboard/, { timeout: 10_000 })

    // --- 3) 关闭 2FA（需密码）→ 登录恢复一步式 ---
    await page.goto('/account/security')
    await page.getByTestId('open-disable-2fa').click()
    await page.getByLabel('账号密码').fill(user.password)
    await page.getByTestId('confirm-disable-2fa').click()
    await expect(page.getByText('两步验证已关闭')).toBeVisible({ timeout: 5_000 })

    await page.evaluate(() => localStorage.clear())
    await page.goto('/login')
    await page.getByLabel('用户名或邮箱').fill(user.username)
    await page.getByLabel('密码', { exact: true }).fill(user.password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.getByText('登录成功')).toBeVisible({ timeout: 5_000 })

    await ctx.close()
  })

  test('account security page requires login', async ({ browser }) => {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto('/account/security')
    await expect(page).toHaveURL(/login/, { timeout: 10_000 })
    await ctx.close()
  })
})
