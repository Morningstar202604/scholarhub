import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

// ESM 下没有 __dirname，用 import.meta.url 派生
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// router-plugin 必须先于 react 执行：先扫描 routes/ 生成 routeTree.gen.ts，再让 react 处理 JSX
export default defineConfig({
  plugins: [
    TanStackRouterVite({
      target: 'react',
      autoCodeSplitting: true,
      routesDirectory: './src/routes',
      generatedRouteTree: './src/routeTree.gen.ts',
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 转发到 backend，避免 CORS 与 cookie 域问题（refresh token cookie path=/api/auth）
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    css: true,
  },
  build: {
    rollupOptions: {
      output: {
        // 用函数式而非对象式：node_modules 中可能不存在的包不会触发拼写错误
        // id 在 vite 里统一规范化为 unix 风格，跨平台安全
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (
            id.includes('/node_modules/react/') ||
            id.includes('/node_modules/react-dom/') ||
            id.includes('/node_modules/scheduler/')
          ) {
            return 'react-vendor'
          }
          if (id.includes('@tanstack')) return 'tanstack-vendor'
          if (id.includes('@radix-ui')) return 'radix-vendor'
          if (id.includes('lucide-react')) return 'lucide-vendor'
          if (id.includes('/node_modules/sonner/')) return 'sonner-vendor'
        },
      },
    },
  },
})
