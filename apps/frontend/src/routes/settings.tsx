import { createFileRoute, Link, redirect } from '@tanstack/react-router'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { TwoFactorSection } from '@/components/settings/two-factor-section'
import { getAuthState, useAuthStore } from '@/lib/auth'

export const Route = createFileRoute('/settings')({
  // 与其他需要登录的页面保持一致：访客进来直接弹回登录页，
  // 而不是渲染一个点什么都 401 的空壳。
  beforeLoad: () => {
    if (!getAuthState().isAuthenticated) {
      throw redirect({ to: '/login', search: { redirect: '/settings' } })
    }
  },
  component: SettingsPage,
})

function SettingsPage() {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-8">
      <h1 className="text-2xl font-semibold">账号设置</h1>

      <Card>
        <CardHeader>
          <CardTitle>资料</CardTitle>
          <CardDescription>当前登录账号的信息。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">用户名</span>
            <span className="font-medium">{user?.username ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">角色</span>
            <span className="font-medium">{user?.is_admin ? '管理员' : '普通用户'}</span>
          </div>
          <p className="pt-2 text-xs text-muted-foreground">
            修改密码请前往{' '}
            <Link to="/account/security" className="underline">
              账号安全
            </Link>
            。
          </p>
        </CardContent>
      </Card>

      <TwoFactorSection />
    </div>
  )
}
