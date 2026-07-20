import { createRootRouteWithContext } from '@tanstack/react-router'
import { QueryClient } from '@tanstack/react-query'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
import { AppShell } from '@/components/layout/AppShell'
import { useAuthStore, type AuthUser } from '@/lib/auth'
import { api } from '@/lib/api'
import { Toaster } from '@/components/ui/sonner'
import type { UserResponse } from '@/lib/types'

interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: async ({ context }) => {
    // 刷新页面后 token 还在但 user 为 null：拉一次 /auth/me 回填 store，
    // 否则 admin 路由守卫会误判跳 /login，AppShell 用户菜单也会消失
    const { token, user } = useAuthStore.getState()
    if (token && !user) {
      try {
        const res = await context.queryClient.fetchQuery<UserResponse>({
          queryKey: ['auth', 'me'],
          queryFn: async () => (await api.get<UserResponse>('/auth/me')).data,
          staleTime: 60_000,
        })
        useAuthStore.getState().setUser({
          id: res.id,
          username: res.username,
          is_admin: res.is_admin,
        } satisfies AuthUser)
      } catch {
        // token 失效或网络错误：清掉避免后续 401 循环
        useAuthStore.getState().logout()
      }
    }
  },
  component: RootLayout,
})

function RootLayout() {
  return (
    <>
      <AppShell />
      <Toaster position="top-right" richColors closeButton />
      {import.meta.env.DEV && <TanStackRouterDevtools />}
    </>
  )
}
