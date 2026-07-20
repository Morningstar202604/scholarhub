import { useState } from 'react'
import { createFileRoute, Link, useNavigate, useSearch } from '@tanstack/react-router'
import { AxiosError } from 'axios'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useLogin } from '@/hooks/api/use-auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { redirect?: string }
  const loginMut = useLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await loginMut.mutateAsync({ username, password })
      toast.success('登录成功')
      void navigate({ to: search.redirect ?? '/dashboard' })
    } catch (err) {
      const msg =
        err instanceof AxiosError
          ? (err.response?.data as { detail?: string })?.detail ?? '登录失败'
          : '登录失败'
      toast.error(msg)
    }
  }

  // OIDC SSO redirect: open /api/auth/oidc/{provider}/login directly.
  // The provider is checked against an allowlist so a polluted env var
  // cannot redirect the user to an attacker-controlled IdP.
  const OIDC_PROVIDERS = ['google', 'github', 'keycloak', 'generic'] as const
  const onOidcLogin = () => {
    const provider = import.meta.env.VITE_OIDC_PROVIDER ?? 'google'
    if (!OIDC_PROVIDERS.includes(provider as (typeof OIDC_PROVIDERS)[number])) {
      toast.error('OIDC provider 配置无效')
      return
    }
    window.location.href = `${api.defaults.baseURL}/auth/oidc/${provider}/login`
  }

  const oidcEnabled = import.meta.env.VITE_OIDC_ENABLED === 'true'

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md items-center">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-2xl">登录</CardTitle>
          <CardDescription>使用账号密码登录 ScholarHUB。</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">用户名或邮箱</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">密码</Label>
                <Link
                  to="/forgot-password"
                  className="text-xs text-muted-foreground hover:text-primary"
                >
                  忘记密码？
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={loginMut.isPending}>
              {loginMut.isPending ? '登录中…' : '登录'}
            </Button>
          </form>

          {oidcEnabled && (
            <>
              <div className="my-4 flex items-center gap-2 text-xs text-muted-foreground">
                <Separator className="flex-1" />
                或
                <Separator className="flex-1" />
              </div>
              <Button variant="outline" className="w-full" onClick={onOidcLogin}>
                使用 SSO 登录
              </Button>
            </>
          )}

          <p className="mt-4 text-center text-sm text-muted-foreground">
            没有账号？{' '}
            <Link to="/register" className="text-primary hover:underline">
              注册
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
