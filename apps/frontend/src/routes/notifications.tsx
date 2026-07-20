import { useState } from 'react'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { CheckCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { getAuthState } from '@/lib/auth'
import {
  useDeleteNotification,
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useUnreadCount,
} from '@/hooks/api/use-modules'
import { extractError } from '@/lib/utils'
import { PageHeader } from '@/components/common/page-header'
import { Pagination } from '@/components/common/pagination'
import { EmptyState, ErrorState, Loading } from '@/components/common/state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

export const Route = createFileRoute('/notifications')({
  beforeLoad: () => {
    if (!getAuthState().isAuthenticated) throw redirect({ to: '/login' })
  },
  component: NotificationsPage,
})

const PAGE_SIZE = 20

function NotificationsPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, refetch } = useNotifications(page, PAGE_SIZE)
  const unread = useUnreadCount()
  const markAllMut = useMarkAllRead()
  const markMut = useMarkRead()
  const deleteMut = useDeleteNotification()

  const onMarkAll = async () => {
    try {
      const res = await markAllMut.mutateAsync()
      toast.success(`已标记 ${res.updated} 条为已读`)
    } catch (err) {
      toast.error(extractError(err, '操作失败'))
    }
  }

  const onMarkRead = async (id: number) => {
    try {
      await markMut.mutateAsync(id)
    } catch (err) {
      toast.error(extractError(err, '标记失败'))
    }
  }

  const onDelete = async (id: number) => {
    try {
      await deleteMut.mutateAsync(id)
      toast.success('已删除')
    } catch (err) {
      toast.error(extractError(err, '删除失败'))
    }
  }

  const unreadCount = unread.data?.unread ?? 0

  return (
    <div>
      <PageHeader
        title="通知"
        description="关注、提交、提及等所有站内消息。"
        actions={
          <Button
            variant="outline"
            onClick={onMarkAll}
            disabled={unreadCount === 0 || markAllMut.isPending}
          >
            <CheckCheck className="h-4 w-4" />
            全部标为已读
          </Button>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-muted-foreground">未读</span>
        <Badge variant={unreadCount > 0 ? 'default' : 'secondary'}>
          {unreadCount}
        </Badge>
      </div>

      {isLoading ? (
        <Loading />
      ) : isError ? (
        <ErrorState message="加载通知失败" onRetry={() => refetch()} />
      ) : !data || data.data.length === 0 ? (
        <EmptyState title="暂无通知" />
      ) : (
        <div className="space-y-3">
          {data.data.map((n) => (
            <Card
              key={n.id}
              // 未读：左侧蓝色竖线区分
              className={
                n.is_read ? 'border-l-0' : 'border-l-4 border-l-primary'
              }
            >
              <CardContent className="flex items-start justify-between gap-3 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{n.title}</p>
                    {!n.is_read && (
                      <Badge variant="default" className="shrink-0">
                        新
                      </Badge>
                    )}
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                      {new Date(n.created_at).toLocaleString()}
                    </span>
                  </div>
                  {n.body && (
                    <p className="mt-1 text-sm text-muted-foreground whitespace-pre-wrap">
                      {n.body}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!n.is_read && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onMarkRead(n.id)}
                      disabled={markMut.isPending}
                    >
                      <CheckCheck className="h-4 w-4" />
                      标为已读
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(n.id)}
                    disabled={deleteMut.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {data && (
        <Pagination
          page={data.meta.page}
          totalPages={data.meta.total_pages}
          onPageChange={setPage}
        />
      )}
    </div>
  )
}
