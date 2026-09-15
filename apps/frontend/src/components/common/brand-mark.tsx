/**
 * 品牌标志（S · 书页流转）。
 *
 * 与 docs/assets/logo-mark.svg 保持同一几何；内联为组件是为了让
 * `currentColor` 生效 —— SVG 通过 <img> 引入时无法继承页面的 text color，
 * 内联后侧边栏切换主题 / 折叠态都能自动跟随文字颜色。
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 240 240"
      className={className}
      role="img"
      aria-label="ScholarHUB"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M 154 86 C 154 68 139 62 120 62 C 99 62 86 73 86 90 C 86 106 99 114 120 120 C 141 126 154 134 154 150 C 154 167 141 178 120 178 C 101 178 86 172 86 154"
        stroke="currentColor"
        strokeWidth={17}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
