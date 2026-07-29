import { useEffect, useState } from 'react'

// 移动端断点：< 768px 视为移动设备（与 Tailwind 默认 md 断点对齐）。
const MOBILE_QUERY = '(max-width: 767px)'

// 初始值同步计算，避免首屏从桌面态闪到移动态（SPA 无 SSR，window 一定存在）。
function getInitialIsMobile(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia(MOBILE_QUERY).matches
}

/**
 * 返回当前是否处于移动视口。
 * 用于在 __root 层切换 MobileAppShell / AppShell，以及页面内做移动专属呈现。
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(getInitialIsMobile)

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY)
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    // 挂载时再同步一次，覆盖首屏后视口可能已变化的情况
    setIsMobile(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return isMobile
}
