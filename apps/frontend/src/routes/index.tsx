import { createFileRoute, Link } from '@tanstack/react-router'
import { BookOpen, Library, LogIn, Plus, Sparkles } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { useResources } from '@/hooks/api/use-modules'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, ErrorState, Loading } from '@/components/common/state'

export const Route = createFileRoute('/')({
  component: HomePage,
})

// 公开首页：不登录也能看内容，登录后才展示工作台入口。
// 首页 = 期刊门面：精选最新资源，而不是把访客直接踢去登录页。
function HomePage() {
  const { isAuthenticated, isAdmin } = useAuth()
  const { data, isLoading, isError, refetch } = useResources({
    page: 1,
    page_size: 9,
    sort: 'created_at',
    order: 'desc',
  })

  const resources = data?.data ?? []

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8">
      {/* 顶部品牌条 */}
      <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-6 w-6 text-primary" />
          <span className="text-lg font-semibold">ScholarHUB</span>
        </div>
        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <Button asChild size="sm">
              <Link to="/dashboard">
                <Plus className="h-4 w-4" /> 进入工作台
              </Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="outline" size="sm">
                <Link to="/login">
                  <LogIn className="h-4 w-4" /> 登录
                </Link>
              </Button>
              <Button asChild size="sm">
                <Link to="/register">注册</Link>
              </Button>
            </>
          )}
        </div>
      </header>

      {/* 期刊门面语 */}
      <section className="mb-8 rounded-2xl border bg-gradient-to-br from-primary/5 to-transparent p-6 sm:p-8">
        <h1 className="mb-2 text-2xl font-bold tracking-tight sm:text-3xl">
          开放学术出版，从这里开始
        </h1>
        <p className="mb-4 max-w-2xl text-sm text-muted-foreground sm:text-base">
          投稿、同行评审、在线出版一体化的开放期刊平台。浏览最新论文，
          或注册成为作者、审稿人与编辑。
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/catalog">
              <Library className="h-4 w-4" /> 浏览全部资源
            </Link>
          </Button>
          {!isAuthenticated && (
            <Button asChild size="sm">
              <Link to="/register">
                <Sparkles className="h-4 w-4" /> 免费注册投稿
              </Link>
            </Button>
          )}
        </div>
      </section>

      {/* 精选资源 */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">最新资源</h2>
          <Button asChild variant="ghost" size="sm">
            <Link to="/catalog">查看全部 →</Link>
          </Button>
        </div>

        {isLoading ? (
          <Loading />
        ) : isError ? (
          <ErrorState message="加载资源失败" onRetry={() => refetch()} />
        ) : resources.length === 0 ? (
          <EmptyState
            title="还没有发布资源"
            description="编辑接受投稿后，论文会第一时间出现在这里。"
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {resources.map((r) => (
              <Link
                key={r.id}
                to="/catalog/$resourceId"
                params={{ resourceId: String(r.id) }}
              >
                <Card className="h-full transition-shadow hover:shadow-md">
                  <CardContent className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <Badge variant="secondary">{r.type}</Badge>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {r.year}
                      </span>
                    </div>
                    <h3 className="line-clamp-2 font-medium leading-snug">
                      {r.title}
                    </h3>
                    <p className="line-clamp-1 text-xs text-muted-foreground">
                      {r.authors.join('、')}
                    </p>
                    <p className="line-clamp-3 text-sm text-muted-foreground">
                      {r.abstract}
                    </p>
                    {r.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {r.tags.slice(0, 3).map((t) => (
                          <Badge key={t} variant="outline">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      <footer className="mt-10 border-t pt-4 text-center text-xs text-muted-foreground">
        ScholarHUB · 开放学术出版平台
        {isAdmin && (
          <span className="ml-2">
            · <Link to="/submissions/pending" className="underline">编辑工作台</Link>
          </span>
        )}
      </footer>
    </div>
  )
}
