import {
  Bell,
  BookOpen,
  ClipboardCheck,
  Heart,
  Home,
  Lightbulb,
  ShieldCheck,
  ScrollText,
  Upload,
  Users,
  type LucideIcon,
  User,
} from 'lucide-react'

export interface MobileTab {
  to: string
  label: string
  icon: LucideIcon
  /** 为 true 时点击不跳转，而是打开"更多"底部抽屉 */
  openSheet?: boolean
}

export interface MobileMoreItem {
  to: string
  label: string
  icon: LucideIcon
  adminOnly?: boolean
}

// 底部 Tab 栏：4 个固定入口。中心 FAB 由外壳单独渲染，不在此列表。
export const MOBILE_TABS: MobileTab[] = [
  { to: '/dashboard', label: '概览', icon: Home },
  { to: '/catalog', label: '目录', icon: BookOpen },
  { to: '/notifications', label: '通知', icon: Bell },
  { to: '/__more', label: '我的', icon: User, openSheet: true },
]

// "更多"底部抽屉的次级导航（按 isAdmin 过滤）。
export const MOBILE_MORE: MobileMoreItem[] = [
  { to: '/submissions', label: '我的提交', icon: ScrollText },
  { to: '/follows', label: '关注与订阅', icon: Heart },
  { to: '/recommendations', label: '推荐', icon: Lightbulb },
  { to: '/review/assignments', label: '审稿工作台', icon: ClipboardCheck },
  { to: '/ingest', label: '导入', icon: Upload },
  { to: '/admin/users', label: '用户管理', icon: Users, adminOnly: true },
  { to: '/admin/audit-logs', label: '审计日志', icon: ShieldCheck, adminOnly: true },
]

// 中心悬浮按钮（FAB）跳转目标：导入（所有登录用户可用，属于创建类操作）。
// 说明：项目暂无独立的"新建投稿"路由，资源创建入口 /catalog/new 仅 admin 可用，
// 故 FAB 统一指向导入页，避免非 admin 用户被重定向到登录页。
export const MOBILE_FAB_TO = '/ingest'
