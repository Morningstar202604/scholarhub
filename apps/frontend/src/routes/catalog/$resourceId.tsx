import { useEffect, useRef, useState } from 'react'
import { createFileRoute, Link, redirect, useNavigate } from '@tanstack/react-router'
import {
  Bookmark,
  BookOpen,
  ChevronLeft,
  ExternalLink,
  Heart,
  MoreVertical,
  Pencil,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/use-auth'
import { useIsMobile } from '@/hooks/use-is-mobile'
import {
  useAuthorFollowStatus,
  useDeleteResource,
  useDisciplineSubscriptionStatus,
  useFollowAuthor,
  useRecordView,
  useReadingProgress,
  useResource,
  useSubscribeDiscipline,
  useUnfollowAuthor,
  useUnsubscribeDiscipline,
  useUpdateResource,
} from '@/hooks/api/use-modules'
import { getAuthState } from '@/lib/auth'
import type { ResourceUpdate } from '@/lib/types'
import { extractError } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState, ErrorState, Loading } from '@/components/common/state'

export const Route = createFileRoute('/catalog/$resourceId')({
  beforeLoad: () => {
    if (!getAuthState().isAuthenticated) throw redirect({ to: '/login' })
  },
  component: CatalogDetailPage,
})

function MetaItem({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}

function CatalogDetailPage() {
  const { resourceId } = Route.useParams()
  const id = Number(resourceId)
  const navigate = useNavigate()
  const { isAdmin } = useAuth()

  const { data, isLoading, isError, refetch } = useResource(id)
  const progress = useReadingProgress(id)
  const recordView = useRecordView()
  const updateMut = useUpdateResource()
  const deleteMut = useDeleteResource()
  const isMobile = useIsMobile()

  // ref guard: avoid double recordView call under React StrictMode
  const viewRecordedRef = useRef(false)
  useEffect(() => {
    if (viewRecordedRef.current) return
    viewRecordedRef.current = true
    void recordView.mutateAsync(id).catch(() => {})
    return () => {
      viewRecordedRef.current = false
    }
  }, [id])

  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  if (isLoading) return <Loading />
  if (isError || !data) {
    return (
      <ErrorState
        message="加载资源失败"
        onRetry={() => refetch()}
      />
    )
  }

  const onDelete = async () => {
    try {
      await deleteMut.mutateAsync(id)
      toast.success('已删除')
      void navigate({ to: '/catalog' })
    } catch {
      toast.error('删除失败')
    }
  }

  return (
    <div className={isMobile ? 'pb-24' : ''}>
      <Link
        to="/catalog"
        className="mb-4 inline-flex items-center text-sm text-muted-foreground hover:text-primary"
      >
        <ChevronLeft className="mr-1 h-4 w-4" />
        返回目录
      </Link>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="secondary">{data.type}</Badge>
            {data.publication_status !== 'published' && (
              <Badge variant="outline">{data.publication_status}</Badge>
            )}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data.authors.join(', ')}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 主体 */}
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">元数据</CardTitle>
            </CardHeader>
            <CardContent>
              <MetaItem label="年份" value={String(data.year)} />
              <MetaItem label="出版物" value={data.venue} />
              <MetaItem label="学科" value={data.discipline} />
              <MetaItem label="子学科" value={data.subdiscipline} />
              <MetaItem label="DOI" value={data.doi} />
              <MetaItem
                label="卷/期/页"
                value={
                  [data.volume, data.issue, data.pages]
                    .filter(Boolean)
                    .join(' / ') || null
                }
              />
              <MetaItem label="语言" value={data.language} />
              <MetaItem label="ISSN" value={data.issn} />
              <MetaItem label="ISBN" value={data.isbn} />
            </CardContent>
          </Card>

          {data.tags.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">标签</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {data.tags.map((t) => (
                    <Badge key={t} variant="outline">
                      {t}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">摘要</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-7 whitespace-pre-wrap">{data.abstract}</p>
            </CardContent>
          </Card>

          {data.preview && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">预览</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-7 whitespace-pre-wrap text-muted-foreground">
                  {data.preview}
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* 右侧操作区（移动端隐藏：操作移入底部固定操作栏） */}
        <div className="space-y-4">
          {!isMobile && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">操作</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button asChild className="w-full">
                  <Link to="/reader/$resourceId" params={{ resourceId: String(id) }}>
                    <BookOpen className="h-4 w-4" />
                    在线阅读
                  </Link>
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" className="w-full">
                      加入阅读列表
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuItem disabled>敬请期待</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                {data.external_url && (
                  <Button asChild variant="outline" className="w-full">
                    <a
                      href={data.external_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="h-4 w-4" />
                      外部链接
                    </a>
                  </Button>
                )}
                {isAdmin && (
                  <>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => setEditOpen(true)}
                    >
                      <Pencil className="h-4 w-4" />
                      编辑
                    </Button>
                    <Button
                      variant="destructive"
                      className="w-full"
                      onClick={() => setDeleteOpen(true)}
                    >
                      <Trash2 className="h-4 w-4" />
                      删除
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">阅读进度</CardTitle>
            </CardHeader>
            <CardContent>
              {progress.isLoading ? (
                <Loading />
              ) : progress.data ? (
                <div className="space-y-1.5 text-sm">
                  <MetaItem
                    label="页码"
                    value={progress.data.page ? String(progress.data.page) : '—'}
                  />
                  <MetaItem
                    label="进度"
                    value={
                      progress.data.progress_percent != null
                        ? `${progress.data.progress_percent}%`
                        : '—'
                    }
                  />
                  <MetaItem
                    label="总时长"
                    value={`${Math.round(progress.data.duration_sec / 60)} 分钟`}
                  />
                  <MetaItem
                    label="访问次数"
                    value={String(progress.data.visit_count)}
                  />
                  <MetaItem
                    label="最近阅读"
                    value={progress.data.last_read_at ?? '—'}
                  />
                  {progress.data.completed && (
                    <Badge variant="secondary">已完成</Badge>
                  )}
                </div>
              ) : (
                <EmptyState title="暂无阅读记录" />
              )}
            </CardContent>
          </Card>

          <FollowCard
            authorName={data.authors[0]}
            discipline={data.discipline}
          />
        </div>
      </div>

      {isMobile && (
        <MobileDetailActions
          resourceId={id}
          isAdmin={isAdmin}
          externalUrl={data.external_url}
          onEdit={() => setEditOpen(true)}
          onDelete={() => setDeleteOpen(true)}
        />
      )}

      {editOpen && data && (
        <EditDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          initial={data}
          onSubmit={async (body) => {
            try {
              await updateMut.mutateAsync({ id, body })
              toast.success('已更新')
              setEditOpen(false)
            } catch (err) {
              toast.error(extractError(err, '更新失败'))
            }
          }}
        />
      )}

      <ConfirmDialog
        open={deleteOpen}
        title="删除资源"
        description="确认删除该资源？此操作不可撤销。"
        confirmText="删除"
        destructive
        onOpenChange={setDeleteOpen}
        onConfirm={onDelete}
      />
    </div>
  )
}

// 编辑表单字段精简：title/authors/year/discipline/abstract/tags/preview
interface EditFormState {
  title: string
  authors: string
  year: string
  discipline: string
  abstract: string
  tags: string
  preview: string
}

function EditDialog({
  open,
  onOpenChange,
  initial,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: {
    title: string
    authors: string[]
    year: number
    discipline: string
    abstract: string
    tags: string[]
    preview: string
  }
  onSubmit: (body: ResourceUpdate) => Promise<void>
}) {
  const [form, setForm] = useState<EditFormState>({
    title: initial.title,
    authors: initial.authors.join(', '),
    year: String(initial.year),
    discipline: initial.discipline,
    abstract: initial.abstract,
    tags: initial.tags.join(', '),
    preview: initial.preview,
  })

  const onSubmitForm = async (e: React.FormEvent) => {
    e.preventDefault()
    const body: ResourceUpdate = {
      title: form.title,
      authors: form.authors
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      year: Number(form.year),
      discipline: form.discipline,
      abstract: form.abstract,
      tags: form.tags
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      preview: form.preview,
    }
    await onSubmit(body)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>编辑资源</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmitForm} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-title">标题</Label>
            <Input
              id="edit-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-authors">作者（逗号分隔）</Label>
            <Input
              id="edit-authors"
              value={form.authors}
              onChange={(e) => setForm({ ...form, authors: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="edit-year">年份</Label>
              <Input
                id="edit-year"
                type="number"
                value={form.year}
                onChange={(e) => setForm({ ...form, year: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-discipline">学科</Label>
              <Input
                id="edit-discipline"
                value={form.discipline}
                onChange={(e) => setForm({ ...form, discipline: e.target.value })}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-abstract">摘要</Label>
            <Textarea
              id="edit-abstract"
              value={form.abstract}
              onChange={(e) => setForm({ ...form, abstract: e.target.value })}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-tags">标签（逗号分隔）</Label>
            <Input
              id="edit-tags"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-preview">预览</Label>
            <Textarea
              id="edit-preview"
              value={form.preview}
              onChange={(e) => setForm({ ...form, preview: e.target.value })}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// 关注作者 + 订阅学科操作卡片。
// 仅在已登录时显示；未登录时整张卡片不渲染（路由层已挡，这里是双保险）。
function FollowCard({
  authorName,
  discipline,
}: {
  authorName: string
  discipline: string
}) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated || !authorName) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">关注</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <FollowAuthorRow authorName={authorName} />
        {discipline && <SubscribeDisciplineRow discipline={discipline} />}
      </CardContent>
    </Card>
  )
}

function FollowAuthorRow({ authorName }: { authorName: string }) {
  const { data } = useAuthorFollowStatus(authorName)
  const followMut = useFollowAuthor()
  const unfollowMut = useUnfollowAuthor()
  const following = data?.following ?? false
  const followersCount = data?.followers_count ?? 0

  const onToggle = async () => {
    const mut = following ? unfollowMut : followMut
    try {
      await mut.mutateAsync(authorName)
      toast.success(following ? `已取消关注 ${authorName}` : `已关注 ${authorName}`)
    } catch (err) {
      toast.error(extractError(err, '操作失败'))
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="min-w-0">
          <span className="text-muted-foreground">作者</span>
          <p className="truncate font-medium">{authorName}</p>
        </span>
        <Button
          variant={following ? 'outline' : 'default'}
          size="sm"
          onClick={onToggle}
          disabled={followMut.isPending || unfollowMut.isPending}
        >
          <Heart className={following ? 'h-4 w-4 fill-current' : 'h-4 w-4'} />
          {following ? '已关注' : '关注'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {followersCount} 人关注
      </p>
    </div>
  )
}

function SubscribeDisciplineRow({ discipline }: { discipline: string }) {
  const { data } = useDisciplineSubscriptionStatus(discipline)
  const subMut = useSubscribeDiscipline()
  const unsubMut = useUnsubscribeDiscipline()
  const subscribed = data?.subscribed ?? false
  const subscribersCount = data?.subscribers_count ?? 0

  const onToggle = async () => {
    const mut = subscribed ? unsubMut : subMut
    try {
      await mut.mutateAsync(discipline)
      toast.success(
        subscribed ? `已取消订阅 ${discipline}` : `已订阅 ${discipline}`,
      )
    } catch (err) {
      toast.error(extractError(err, '操作失败'))
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="min-w-0">
          <span className="text-muted-foreground">学科</span>
          <p className="truncate font-medium">{discipline}</p>
        </span>
        <Button
          variant={subscribed ? 'outline' : 'default'}
          size="sm"
          onClick={onToggle}
          disabled={subMut.isPending || unsubMut.isPending}
        >
          <Bookmark className={subscribed ? 'h-4 w-4 fill-current' : 'h-4 w-4'} />
          {subscribed ? '已订阅' : '订阅'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {subscribersCount} 人订阅
      </p>
    </div>
  )
}

// 移动端底部固定操作栏：在线阅读（主操作）+ 更多菜单（外部链接/编辑/删除）。
// 仅移动端渲染；桌面端沿用右侧"操作"卡片，互不复用。
function MobileDetailActions({
  resourceId,
  isAdmin,
  externalUrl,
  onEdit,
  onDelete,
}: {
  resourceId: number
  isAdmin: boolean
  externalUrl?: string | null
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 flex items-center gap-2 border-t bg-background/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur">
      <Button asChild className="flex-1">
        <Link to="/reader/$resourceId" params={{ resourceId: String(resourceId) }}>
          <BookOpen className="h-4 w-4" />
          在线阅读
        </Link>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label="更多操作">
            <MoreVertical className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          {externalUrl && (
            <DropdownMenuItem asChild>
              <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4" />
                外部链接
              </a>
            </DropdownMenuItem>
          )}
          {isAdmin && (
            <>
              <DropdownMenuItem onClick={onEdit}>
                <Pencil className="h-4 w-4" />
                编辑
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={onDelete}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
                删除
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
