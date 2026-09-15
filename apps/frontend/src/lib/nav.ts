import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  auth?: boolean
  adminOnly?: boolean
}

/**
 * 侧边栏高亮解析：**最长前缀胜出**。
 *
 * - `/submissions/pending` 同时匹配「我的提交」(`/submissions`) 与
 *   「编辑工作台」(`/submissions/pending`)，取更长的那个，避免编辑工作台
 *   页面误高亮成"我的提交"（语义归属错误）。
 * - 段级匹配（`===` 或 `${to}/` 前缀）而非裸 `startsWith`，避免
 *   `/submissionsfoo` 误匹配 `/submissions` 这类假阳性。
 *
 * 抽成纯函数是为了可测：这段逻辑曾内联在 AppShell 组件里，无法单测覆盖。
 */
export function resolveActiveNavPath(
  pathname: string,
  items: NavItem[],
): string | undefined {
  return items
    .filter((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
    .sort((a, b) => b.to.length - a.to.length)[0]?.to
}
