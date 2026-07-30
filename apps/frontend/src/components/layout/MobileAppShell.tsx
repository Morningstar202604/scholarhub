import { useEffect, useState, type ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from '@tanstack/react-router'
import { BookOpen, LogOut, Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/use-auth'
import { useLogout } from '@/hooks/api/use-auth'
import { useUnreadCount } from '@/hooks/api/use-modules'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/theme-toggle'
import { ModuleErrorBoundary } from '@/components/common/error-boundary'
import { MOBILE_TABS, MOBILE_MORE, MOBILE_FAB_TO, type MobileTab } from './mobile-nav'

// 底部抽屉：自带遮罩、ESC 关闭、打开时锁 body 滚动。移动原生交互，不依赖居中 Dialog。
function BottomSheet({
  open,
  onClose,
  children,
}: {
  open: boolean
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="更多">
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" onClick={onClose} />
      <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-2xl border-t bg-background p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] animate-in slide-in-from-bottom duration-200">
        {children}
      </div>
    </div>
  )
}

function MobileTabButton({
  tab,
  active,
  badge,
  onClick,
}: {
  tab: MobileTab
  active: boolean
  badge?: number
  onClick: () => void
}) {
  const Icon = tab.icon
  const showBadge = tab.to === '/notifications' && (badge ?? 0) > 0
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex min-h-[44px] flex-col items-center justify-center gap-0.5 text-xs',
        active ? 'text-primary' : 'text-muted-foreground',
      )}
    >
      <span className="relative">
        <Icon className="h-5 w-5" />
        {showBadge && (
          <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-destructive" />
        )}
      </span>
      <span>{tab.label}</span>
    </button>
  )
}

export function MobileAppShell() {
  const [sheetOpen, setSheetOpen] = useState(false)
  const { isAuthenticated, isAdmin, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const logoutMut = useLogout()
  const { data: unread } = useUnreadCount({ enabled: isAuthenticated })

  const moreItems = MOBILE_MORE.filter((m) => !m.adminOnly || isAdmin)

  // 认证页（登录/注册/找回密码/验证邮箱）不展示底部 Tab 栏与 FAB，避免未登录时露出需鉴权入口
  const isAuthPage = [
    '/login',
    '/register',
    '/forgot-password',
    '/reset-password',
    '/verify-email',
  ].some((p) => location.pathname.startsWith(p))
  const showChrome = !isAuthPage

  // 路由切换后关闭抽屉，避免点击导航后抽屉仍遮挡内容
  useEffect(() => {
    setSheetOpen(false)
  }, [location.pathname])

  const isActive = (to: string) =>
    to !== '/__more' && (location.pathname === to || location.pathname.startsWith(to + '/'))

  const onLogout = async () => {
    try {
      await logoutMut.mutateAsync()
      toast.success('已退出登录')
    } catch {
      // backend 失败也清本地
    }
    setSheetOpen(false)
    void navigate({ to: '/login' })
  }

  const go = (to: string) => {
    setSheetOpen(false)
    void navigate({ to })
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* 紧凑头部：仅 logo + 主题切换（移动端不堆功能） */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <BookOpen className="h-5 w-5 shrink-0" />
          <span>ScholarHUB</span>
        </Link>
        <ThemeToggle />
      </header>

      {/* 内容区：移动端单列、限宽、底部留白避开 Tab 栏 */}
      <main className={cn('flex-1 overflow-y-auto', showChrome ? 'pb-24' : 'pb-4')}>
        <div className="mx-auto w-full max-w-screen-sm px-4 py-4">
          {/* 页面级错误边界：崩溃时底部 Tab 栏仍可用，换页自动复位 */}
          <ModuleErrorBoundary name="页面" resetKeys={[location.pathname]}>
            <Outlet />
          </ModuleErrorBoundary>
        </div>
      </main>

      {/* 中心悬浮按钮：仅登录用户且在非认证页可见，跳导入（创建类操作） */}
      {showChrome && isAuthenticated && (
        <Button
          aria-label="导入"
          onClick={() => go(MOBILE_FAB_TO)}
          className="fixed bottom-20 left-1/2 z-40 h-14 w-14 -translate-x-1/2 rounded-full shadow-lg"
          size="icon"
        >
          <Plus className="h-6 w-6" />
        </Button>
      )}

      {/* 底部 Tab 栏：4 等分，中心 FAB 浮于其上（仅非认证页） */}
      {showChrome && (
        <nav
          className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-4 items-stretch border-t bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
          aria-label="主导航"
        >
          {MOBILE_TABS.map((tab) => (
            <MobileTabButton
              key={tab.to}
              tab={tab}
              active={tab.openSheet ? sheetOpen : isActive(tab.to)}
              badge={unread?.unread}
              onClick={() => (tab.openSheet ? setSheetOpen(true) : go(tab.to))}
            />
          ))}
        </nav>
      )}

      {/* "更多"底部抽屉 */}
      <BottomSheet open={sheetOpen} onClose={() => setSheetOpen(false)}>
        {isAuthenticated && user ? (
          <>
            <div className="mb-3 flex items-center gap-3 border-b pb-3">
              <Avatar className="h-10 w-10">
                <AvatarFallback>{user.username.slice(0, 2).toUpperCase()}</AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{user.username}</div>
                <div className="text-xs text-muted-foreground">已登录</div>
              </div>
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                aria-label="关闭"
                className="text-muted-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex flex-col">
              {moreItems.map((item) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.to}
                    type="button"
                    onClick={() => go(item.to)}
                    className="flex min-h-[48px] items-center gap-3 rounded-md px-2 text-left text-sm hover:bg-accent"
                  >
                    <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />
                    <span>{item.label}</span>
                  </button>
                )
              })}
              <button
                type="button"
                onClick={onLogout}
                className="mt-1 flex min-h-[48px] items-center gap-3 rounded-md px-2 text-left text-sm text-destructive hover:bg-destructive/10"
              >
                <LogOut className="h-5 w-5 shrink-0" />
                <span>退出登录</span>
              </button>
            </div>
          </>
        ) : (
          <div className="flex flex-col gap-3 py-2">
            <Button asChild className="min-h-[44px]">
              <Link to="/login" onClick={() => setSheetOpen(false)}>
                登录
              </Link>
            </Button>
            <Button asChild variant="outline" className="min-h-[44px]">
              <Link to="/register" onClick={() => setSheetOpen(false)}>
                注册
              </Link>
            </Button>
          </div>
        )}
      </BottomSheet>
    </div>
  )
}
