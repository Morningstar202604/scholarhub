import { useState } from 'react'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { getAuthState } from '@/lib/auth'
import { useDoiConfig, useDoiStatus, useRegisterDoi } from '@/hooks/api/use-modules'
import type { DoiStatusResponse } from '@/lib/types'
import { extractError } from '@/lib/utils'
import { PageHeader } from '@/components/common/page-header'
import { Loading } from '@/components/common/state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export const Route = createFileRoute('/admin/doi')({
  beforeLoad: () => {
    if (!getAuthState().isAdmin) throw redirect({ to: '/login' })
  },
  component: AdminDoiPage,
})

const STATE_LABELS: Record<DoiStatusResponse['state'], string> = {
  none: '未注册',
  pending: '注册中',
  completed: '已完成',
  failed: '失败',
}

function AdminDoiPage() {
  const config = useDoiConfig()
  const register = useRegisterDoi()

  const [resourceId, setResourceId] = useState('')
  const [suffix, setSuffix] = useState('')
  const [statusId, setStatusId] = useState('')
  const statusQuery = useDoiStatus(Number(statusId) || 0, statusId !== '')

  const onRegister = async () => {
    const id = Number(resourceId)
    if (!id) {
      toast.error('请输入资源 ID')
      return
    }
    try {
      const result = await register.mutateAsync({
        resource_id: id,
        doi_suffix: suffix.trim() || undefined,
      })
      toast.success(`DOI 已提交：${result.doi}（${STATE_LABELS[result.state as DoiStatusResponse['state']] ?? result.state}）`)
      setStatusId(String(id))
      setResourceId('')
      setSuffix('')
    } catch (err) {
      toast.error(extractError(err, 'DOI 注册失败（未配置 DataCite 时端点返回 501）'))
    }
  }

  const onCheckStatus = () => {
    const id = Number(statusId)
    if (!id) {
      toast.error('请输入资源 ID')
      return
    }
    setStatusId(String(id))
  }

  return (
    <div>
      <PageHeader
        title="DOI 管理"
        description="DataCite DOI 注册与状态查询。注册需要配置 SCHOLARHUB_DATACITE_PREFIX 与 SCHOLARHUB_DATACITE_API_KEY。"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">配置状态</CardTitle>
              <CardDescription>GET /doi/config</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void config.refetch()}
              disabled={config.isFetching}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {config.isLoading ? (
              <Loading />
            ) : (
              <>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">DataCite</span>
                  <Badge variant={config.data?.enabled ? 'secondary' : 'outline'}>
                    {config.data?.enabled ? '已启用' : '未配置'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">DOI 前缀</span>
                  <span className="font-mono text-xs">{config.data?.prefix}</span>
                </div>
                {config.data && !config.data.enabled && (
                  <p className="text-xs text-muted-foreground">
                    未配置时 POST /doi/register 会返回 501，属于预期行为。
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">注册 DOI</CardTitle>
            <CardDescription>为目录资源铸造新 DOI（需 admin）。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="doi-resource-id">资源 ID</Label>
                <Input
                  id="doi-resource-id"
                  type="number"
                  min={1}
                  value={resourceId}
                  onChange={(e) => setResourceId(e.target.value)}
                  placeholder="12"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="doi-suffix">DOI 后缀（可选）</Label>
                <Input
                  id="doi-suffix"
                  value={suffix}
                  onChange={(e) => setSuffix(e.target.value)}
                  placeholder="art-2026-001"
                />
              </div>
            </div>
            <Button onClick={() => void onRegister()} disabled={register.isPending || !resourceId}>
              {register.isPending ? '提交中…' : '注册'}
            </Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">查询注册状态</CardTitle>
            <CardDescription>GET /doi/{'{'}resource_id{'}'}/status</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex max-w-md gap-2">
              <Input
                type="number"
                min={1}
                value={statusId}
                onChange={(e) => setStatusId(e.target.value)}
                placeholder="资源 ID"
              />
              <Button variant="outline" onClick={onCheckStatus} disabled={!statusId}>
                查询
              </Button>
            </div>
            {statusId !== '' &&
              (statusQuery.isLoading ? (
                <Loading />
              ) : statusQuery.data ? (
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <Badge variant="secondary">
                    {STATE_LABELS[statusQuery.data.state]}
                  </Badge>
                  {statusQuery.data.doi ? (
                    <a
                      href={`https://doi.org/${statusQuery.data.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-xs text-primary hover:underline"
                    >
                      {statusQuery.data.doi}
                    </a>
                  ) : (
                    <span className="text-muted-foreground">尚无 DOI</span>
                  )}
                  {statusQuery.data.message && (
                    <span className="text-xs text-muted-foreground">{statusQuery.data.message}</span>
                  )}
                </div>
              ) : (
                <p className="text-sm text-destructive">
                  {extractError(statusQuery.error, '查询失败')}
                </p>
              ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
