import { defineConfig, devices } from '@playwright/test'

// E2E 配置：默认走系统 Chrome（沙箱中 google-chrome-stable 已就绪）。
// 后端走 SQLite + development 模式（见 apps/backend/e2e_run_server.py），
// 前端复用 vite dev server（5173）。两者都已由外部启动时 reuseExistingServer 兜底。
const FRONTEND_URL = process.env.E2E_FRONTEND_URL ?? 'http://localhost:5173'
const BACKEND_URL = process.env.E2E_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false, // 共享 SQLite 单库，串行更稳
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // video 关闭：录制需要 ffmpeg，沙箱不一定有；trace + screenshot 已足够定位失败。
    video: 'off',
    // 用 Playwright 自带 chromium（npm install 后已下载）；
    // 沙箱无系统 Chrome，故不指定 channel。
    launchOptions: {
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    },
  },
  projects: [
    {
      name: 'chromium',
      // 桌面项目跑全部用例；移动专用用例交给 mobile 项目（iPhone 13 视口）单独跑，
      // 避免桌面视口下误判"底部 Tab 栏必须可见"等移动断言。
      testIgnore: ['**/mobile-shell.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile',
      // 仅跑移动专用用例：iPhone 13 视口（390×844）触发 useIsMobile() → 渲染 MobileAppShell。
      // 用 chromium 而非设备默认的 webkit：沙箱仅缓存 chromium，且移动判定靠视口宽度
      // （matchMedia max-width:767px）而非内核，chromium 下断言等价。
      testMatch: '**/mobile-shell.spec.ts',
      use: { ...devices['iPhone 13'], browserName: 'chromium' },
    },
  ],
  webServer: [
    {
      command: 'cd ../backend && uv run python e2e_run_server.py',
      url: `${BACKEND_URL}/api/health`,
      // 默认复用外部已起的服务（沙箱已起 backend+vite），仅当 E2E_SPAWN_SERVER=1 时才自启。
      reuseExistingServer: process.env.E2E_SPAWN_SERVER !== '1',
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --strictPort=false',
      url: FRONTEND_URL,
      reuseExistingServer: process.env.E2E_SPAWN_SERVER !== '1',
      timeout: 60_000,
    },
  ],
})
