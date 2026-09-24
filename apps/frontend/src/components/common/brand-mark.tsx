/**
 * 品牌图形标（书页之 S）。
 *
 * 与 docs/assets/logo-mark.svg 保持同一几何；内联为组件是为了让
 * `currentColor` 生效 —— SVG 通过 <img> 引入时无法继承页面的 text color，
 * 内联后侧边栏切换主题 / 折叠态都能自动跟随文字颜色。
 * 金色翻页角为品牌点缀色（#C7A24B），深浅主题下均与主色协调。
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
        d="M 176 72 C 176 54 158 44 120 44 C 84 44 64 58 64 80 C 64 100 80 110 106 116 C 134 122 176 134 176 164 C 176 188 156 196 120 196 C 86 196 64 184 64 168"
        stroke="currentColor"
        strokeWidth={25}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M 132 184 C 152 176 168 160 172 140 C 164 164 148 176 124 180 Z"
        fill="#C7A24B"
      />
    </svg>
  )
}
