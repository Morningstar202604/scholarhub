import { createFileRoute } from '@tanstack/react-router'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { TwoFactorSection } from '@/components/settings/two-factor-section'

export const Route = createFileRoute('/settings')({
  component: SettingsPage,
})

function SettingsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 py-8">
      <h1 className="text-2xl font-semibold">账号设置</h1>

      <Card>
        <CardHeader>
          <CardTitle>资料</CardTitle>
          <CardDescription>显示名、邮箱等基础信息（开发中）。</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          基础资料编辑走 PATCH /users/me，目前通过 /api/auth/me 的派生数据展示。
        </CardContent>
      </Card>

      <TwoFactorSection />
    </div>
  )
}
