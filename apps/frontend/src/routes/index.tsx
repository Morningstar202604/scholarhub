import { createFileRoute, redirect } from '@tanstack/react-router'
import { getAuthState } from '@/lib/auth'

export const Route = createFileRoute('/')({
  // 已登录跳 /dashboard，未登录跳 /login；root layout 已渲染，这里只做分流
  beforeLoad: () => {
    const { isAuthenticated } = getAuthState()
    throw redirect({ to: isAuthenticated ? '/dashboard' : '/login' })
  },
  component: () => null,
})
