import { useEffect, useState } from 'react'
import { createFileRoute, Link, useNavigate, useSearch } from '@tanstack/react-router'
import { AxiosError } from 'axios'
import { toast } from 'sonner'
import { useResendVerification, useVerifyEmail } from '@/hooks/api/use-auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/verify-email')({
  component: VerifyEmailPage,
})

function VerifyEmailPage() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { token?: string; email?: string }
  const verifyMut = useVerifyEmail()
  const resendMut = useResendVerification()
  const [token, setToken] = useState(search.token ?? '')
  const [email, setEmail] = useState(search.email ?? '')
  const [done, setDone] = useState(false)

  // Strip the token query param from the URL as soon as it is read, so it
  // does not linger in browser history or get captured in screenshots.
  useEffect(() => {
    if (search.token && window.location.search) {
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [search.token])

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await verifyMut.mutateAsync({ token })
      setDone(true)
      toast.success('邮箱验证成功，请登录')
    } catch (err) {
      const msg =
        err instanceof AxiosError
          ? (err.response?.data as { detail?: string })?.detail ?? '验证失败'
          : '验证失败'
      toast.error(msg)
    }
  }

  const onResend = async () => {
    if (!email) {
      toast.error('请填写邮箱')
      return
    }
    try {
      await resendMut.mutateAsync({ email })
      toast.success('如果该邮箱已注册，验证邮件已重新发送')
    } catch {
      toast.error('发送失败，请稍后重试')
    }
  }

  if (done) {
    return (
      <div className="mx-auto flex min-h-[80vh] max-w-md items-center">
        <Card className="w-full">
          <CardHeader>
            <CardTitle>验证成功</CardTitle>
            <CardDescription>邮箱验证完成，可以登录了。</CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" onClick={() => void navigate({ to: '/login' })}>
              前往登录
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md items-center">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-2xl">验证邮箱</CardTitle>
          <CardDescription>
            输入邮件中的验证 token，或重新发送验证邮件。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={onVerify} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="token">验证 Token</Label>
              <Input
                id="token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="邮件链接里的 token 参数"
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={verifyMut.isPending}>
              {verifyMut.isPending ? '验证中…' : '验证'}
            </Button>
          </form>
          <div className="space-y-2 border-t pt-4">
            <Label htmlFor="email">没收到邮件？重新发送</Label>
            <div className="flex gap-2">
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="你的注册邮箱"
              />
              <Button
                type="button"
                variant="outline"
                onClick={onResend}
                disabled={resendMut.isPending}
              >
                {resendMut.isPending ? '发送中…' : '发送'}
              </Button>
            </div>
          </div>
          <p className="text-center text-sm text-muted-foreground">
            <Link to="/login" className="text-primary hover:underline">
              返回登录
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
