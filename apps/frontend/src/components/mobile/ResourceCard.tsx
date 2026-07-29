import { Link } from '@tanstack/react-router'
import { Badge } from '@/components/ui/badge'
import type { ResourceResponse } from '@/lib/types'

// 移动端目录卡片：竖向堆叠、大触摸目标、点击整卡进入详情。
// 与桌面表格是两套完全不同的呈现，不共享勾选/批量逻辑。
export function ResourceCard({ resource }: { resource: ResourceResponse }) {
  const authors =
    resource.authors.length > 2
      ? `${resource.authors.slice(0, 2).join(', ')} et al.`
      : resource.authors.join(', ')

  return (
    <Link
      to="/catalog/$resourceId"
      params={{ resourceId: String(resource.id) }}
      className="block rounded-xl border bg-card p-4 transition active:scale-[0.99]"
    >
      <p className="line-clamp-2 font-medium leading-snug">{resource.title}</p>
      {authors && (
        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{authors}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary" className="text-[10px]">
          {resource.type}
        </Badge>
        <span>{resource.year}</span>
        {resource.discipline && (
          <>
            <span>·</span>
            <span className="line-clamp-1">{resource.discipline}</span>
          </>
        )}
      </div>
    </Link>
  )
}
