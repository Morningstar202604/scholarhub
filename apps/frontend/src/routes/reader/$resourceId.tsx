import { useEffect, useRef, useState } from 'react'
import { createFileRoute, Link, redirect, useNavigate } from '@tanstack/react-router'
import { ChevronLeft, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { getAuthState } from '@/lib/auth'
import {
  useReadingProgress,
  useRemoveFromHistory,
  useResource,
  useUpdateProgress,
} from '@/hooks/api/use-modules'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState, ErrorState, Loading } from '@/components/common/state'

// Restrict reader iframe to https: scheme so data:/blob:/javascript:
// URLs cannot execute content inside the PDF viewer frame.
function isSafeDownloadUrl(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:'
  } catch {
    return false
  }
}

export const Route = createFileRoute('/reader/$resourceId')({
  beforeLoad: () => {
    if (!getAuthState().isAuthenticated) throw redirect({ to: '/login' })
  },
  component: ReaderPage,
})

function ReaderPage() {
  const { resourceId } = Route.useParams()
  const id = Number(resourceId)
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch } = useResource(id)
  const progress = useReadingProgress(id)
  const updateMut = useUpdateProgress()
  const removeMut = useRemoveFromHistory()

  const [page, setPage] = useState(1)
  const [progressPercent, setProgressPercent] = useState(0)
  const [completed, setCompleted] = useState(false)
  // 本地累加器：仅跟踪本次会话新增的秒数，flush 后清零
  const [localDuration, setLocalDuration] = useState(0)
  const [removeOpen, setRemoveOpen] = useState(false)

  // 从服务端进度初始化本地状态（仅首次加载时）
  useEffect(() => {
    if (progress.data) {
      setPage(progress.data.page ?? 1)
      setProgressPercent(progress.data.progress_percent ?? 0)
      setCompleted(progress.data.completed)
    }
  }, [progress.data])

  // 用 ref 持有最新值，让 setInterval 回调读取时不被闭包冻结
  const stateRef = useRef({ page, progressPercent, completed, localDuration })
  stateRef.current = { page, progressPercent, completed, localDuration }

  const flush = async () => {
    const s = stateRef.current
    if (s.localDuration === 0) return
    try {
      await updateMut.mutateAsync({
        resourceId: id,
        body: {
          page: s.page,
          progress_percent: s.progressPercent,
          duration_sec: s.localDuration,
          completed: s.completed,
        },
      })
      setLocalDuration(0)
    } catch {
      // flush 失败静默，下个周期会重试
    }
  }

  // 每秒累加时长；每 30s 自动 flush
  useEffect(() => {
    const ticker = setInterval(() => {
      setLocalDuration((s) => s + 1)
    }, 1000)
    const flusher = setInterval(() => {
      void flush()
    }, 30_000)
    return () => {
      clearInterval(ticker)
      clearInterval(flusher)
      // unmount 时立即上报最后一次累积的进度，避免丢失最多 29s
      void flush()
    }
  }, [])

  // 翻页前立即 flush 旧状态
  const goToPage = (newPage: number) => {
    void flush()
    setPage(Math.max(1, newPage))
  }

  const onManualUpdate = async () => {
    await flush()
    toast.success('进度已保存')
  }

  const onRemove = async () => {
    try {
      await removeMut.mutateAsync(id)
      toast.success('已从阅读历史移除')
      void navigate({ to: '/catalog' })
    } catch {
      toast.error('移除失败')
    }
  }

  if (isLoading) return <Loading />
  if (isError || !data) {
    return <ErrorState message="加载资源失败" onRetry={() => refetch()} />
  }

  const totalDuration = (progress.data?.duration_sec ?? 0) + localDuration

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* 顶部标题栏 */}
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2 sm:gap-3">
        <Link
          to="/catalog/$resourceId"
          params={{ resourceId: String(id) }}
          className="inline-flex shrink-0 items-center text-sm text-muted-foreground hover:text-primary"
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          返回详情
        </Link>
        <span className="min-w-0 flex-1 text-sm font-medium line-clamp-1">{data.title}</span>
        {data.type && <Badge variant="secondary">{data.type}</Badge>}
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        {/* PDF 主体 */}
        <div className="flex-1 overflow-hidden p-4">
          {data.download_url && isSafeDownloadUrl(data.download_url) ? (
            <iframe
              src={data.download_url}
              title={data.title}
              className="h-[60vh] w-full rounded-md border lg:h-full"
              sandbox="allow-same-origin allow-popups"
            />
          ) : (
            <EmptyState
              title="暂无可阅读文件"
              description={
                data.download_url
                  ? '该资源下载链接协议不安全，已阻止加载。'
                  : '该资源未提供下载链接。'
              }
            />
          )}
        </div>

        {/* 右侧进度栏：桌面端固定侧栏，移动端堆叠到下方全宽 */}
        <aside className="w-full shrink-0 overflow-y-auto border-t p-4 lg:w-72 lg:border-l lg:border-t-0">
          <Card className="mb-4">
            <CardHeader>
              <CardTitle className="text-base">阅读进度</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="page">页码</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="page"
                    type="number"
                    min={1}
                    value={page}
                    onChange={(e) => setPage(Number(e.target.value))}
                    className="h-8 w-20"
                  />
                  <Button size="sm" variant="outline" onClick={() => goToPage(page - 1)}>
                    上一页
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => goToPage(page + 1)}>
                    下一页
                  </Button>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="progress">
                  进度：{progressPercent}%
                </Label>
                <input
                  id="progress"
                  type="range"
                  min={0}
                  max={100}
                  value={progressPercent}
                  onChange={(e) => setProgressPercent(Number(e.target.value))}
                  className="w-full"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="completed"
                  type="checkbox"
                  checked={completed}
                  onChange={(e) => setCompleted(e.target.checked)}
                />
                <Label htmlFor="completed" className="cursor-pointer">
                  已读完
                </Label>
              </div>

              <div className="space-y-1 border-t pt-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">总时长</span>
                  <span>{Math.round(totalDuration / 60)} 分钟</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">最近阅读</span>
                  <span>{progress.data?.last_read_at ?? '—'}</span>
                </div>
              </div>

              <Button
                className="w-full"
                size="sm"
                onClick={onManualUpdate}
                disabled={updateMut.isPending}
              >
                {updateMut.isPending ? '保存中…' : '保存进度'}
              </Button>
            </CardContent>
          </Card>

          <Button
            variant="outline"
            className="w-full text-destructive"
            onClick={() => setRemoveOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            移除阅读历史
          </Button>
        </aside>
      </div>

      <ConfirmDialog
        open={removeOpen}
        title="移除阅读历史"
        description="确认移除该资源的阅读历史？此操作不可撤销。"
        confirmText="移除"
        destructive
        onOpenChange={setRemoveOpen}
        onConfirm={onRemove}
      />
    </div>
  )
}
