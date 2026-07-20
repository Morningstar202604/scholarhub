import { ThemeProvider as NextThemesProvider } from 'next-themes'
import type { ReactNode } from 'react'

// next-themes 提供 system 偏好跟随 + localStorage 持久化
// attribute="class" 对应 index.css 里的 .dark 自定义变体
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  )
}
