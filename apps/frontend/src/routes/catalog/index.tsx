import { useState } from 'react'
import { createFileRoute, Link, useNavigate, useSearch } from '@tanstack/react-router'
import { Download, Plus, SlidersHorizontal } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/use-auth'
import { useIsMobile } from '@/hooks/use-is-mobile'
import { exportResources, useResources } from '@/hooks/api/use-modules'
import type { ResourceType } from '@/lib/types'
import { PageHeader } from '@/components/common/page-header'
import { EmptyState, ErrorState, Loading } from '@/components/common/state'
import { Pagination } from '@/components/common/pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ResourceCard } from '@/components/mobile/ResourceCard'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export const Route = createFileRoute('/catalog/')({
  component: CatalogListPage,
})

interface CatalogSearch {
  q?: string
  type?: ResourceType
  discipline?: string
  year?: number
  page?: number
}

const TYPE_OPTIONS: { value: ResourceType | 'all'; label: string }[] = [
  { value: 'all', label: '全部类型' },
  { value: 'paper', label: '论文' },
  { value: 'book', label: '图书' },
  { value: 'dataset', label: '数据集' },
  { value: 'tutorial', label: '教程' },
]

const EXPORT_FORMATS = ['bibtex', 'ris', 'csv', 'json'] as const

function CatalogListPage() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as CatalogSearch
  const { isAdmin } = useAuth()
  const isMobile = useIsMobile()

  const params = {
    q: search.q || undefined,
    type: search.type,
    discipline: search.discipline || undefined,
    year: search.year,
    page: search.page || 1,
    page_size: 10,
  }

  const { data, isLoading, isError, refetch } = useResources(params)
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  // 筛选条件写到 URL，replace 避免每次筛选都污染历史
  const updateSearch = (patch: Partial<CatalogSearch>) => {
    void navigate({
      to: '/catalog',
      search: { ...search, ...patch },
      replace: true,
    })
  }

  const allIds = data?.data.map((r) => r.id) ?? []
  const allSelected = allIds.length > 0 && selectedIds.length === allIds.length

  const toggleAll = () => {
    setSelectedIds(allSelected ? [] : allIds)
  }

  const toggleOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const onExport = async (format: (typeof EXPORT_FORMATS)[number]) => {
    if (selectedIds.length === 0) {
      toast.error('请先选择资源')
      return
    }
    try {
      await exportResources(selectedIds, format)
      toast.success(`已导出 ${selectedIds.length} 条为 ${format.toUpperCase()}`)
    } catch {
      toast.error('导出失败')
    }
  }

  return (
    <div>
      <PageHeader
        title="资源目录"
        description="浏览 ScholarHUB 中所有学术资源。"
        actions={
          isAdmin ? (
            <Button asChild>
              <Link to="/catalog/new">
                <Plus className="h-4 w-4" />
                新建资源
              </Link>
            </Button>
          ) : null
        }
      />

      {/* 桌面端：筛选常驻卡片（md 及以上） */}
      {!isMobile && (
        <Card className="mb-4">
          <CardContent className="pt-0">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">搜索</label>
                <Input
                  placeholder="标题/作者/摘要"
                  defaultValue={search.q ?? ''}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      updateSearch({
                        q: (e.target as HTMLInputElement).value,
                        page: 1,
                      })
                    }
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">类型</label>
                <Select
                  value={search.type ?? 'all'}
                  onValueChange={(v) =>
                    updateSearch({
                      type: v === 'all' ? undefined : (v as ResourceType),
                      page: 1,
                    })
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TYPE_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">学科</label>
                <Input
                  placeholder="如 computer science"
                  defaultValue={search.discipline ?? ''}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      updateSearch({
                        discipline: (e.target as HTMLInputElement).value,
                        page: 1,
                      })
                    }
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">年份</label>
                <Input
                  type="number"
                  placeholder="如 2024"
                  defaultValue={search.year ?? ''}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const v = (e.target as HTMLInputElement).value
                      updateSearch({
                        year: v ? Number(v) : undefined,
                        page: 1,
                      })
                    }
                  }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 移动端：筛选收进可折叠面板，默认收起，避免挤占浏览空间 */}
      {isMobile && <MobileFilters search={search} updateSearch={updateSearch} />}

      {/* 批量选择/导出是桌面管理操作，移动端隐藏以保持浏览专注 */}
      {!isMobile && selectedIds.length > 0 && (
        <div className="mb-3 flex items-center justify-between rounded-md border bg-muted/40 px-4 py-2">
          <span className="text-sm">已选 {selectedIds.length} 项</span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Download className="h-4 w-4" />
                导出为…
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {EXPORT_FORMATS.map((f) => (
                <DropdownMenuItem key={f} onClick={() => onExport(f)}>
                  {f.toUpperCase()}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {isLoading ? (
        <Loading />
      ) : isError ? (
        <ErrorState message="加载资源失败" onRetry={() => refetch()} />
      ) : !data || data.data.length === 0 ? (
        <EmptyState title="暂无资源" description="尝试调整筛选条件。" />
      ) : isMobile ? (
        // 移动端：卡片列表（独立设计，无批量勾选）
        <div className="space-y-3">
          {data.data.map((r) => (
            <ResourceCard key={r.id} resource={r} />
          ))}
        </div>
      ) : (
        // 桌面端：表格
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="全选"
                    />
                  </TableHead>
                  <TableHead>标题</TableHead>
                  <TableHead>作者</TableHead>
                  <TableHead className="w-16">年份</TableHead>
                  <TableHead>学科</TableHead>
                  <TableHead className="w-20">类型</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.data.map((r) => {
                  const authors =
                    r.authors.length > 2
                      ? `${r.authors.slice(0, 2).join(', ')} et al.`
                      : r.authors.join(', ')
                  return (
                    <TableRow
                      key={r.id}
                      data-state={selectedIds.includes(r.id) ? 'selected' : undefined}
                    >
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(r.id)}
                          onChange={() => toggleOne(r.id)}
                          aria-label={`选择 ${r.title}`}
                        />
                      </TableCell>
                      <TableCell>
                        <Link
                          to="/catalog/$resourceId"
                          params={{ resourceId: String(r.id) }}
                          className="font-medium hover:text-primary"
                        >
                          {r.title}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {authors}
                      </TableCell>
                      <TableCell>{r.year}</TableCell>
                      <TableCell>{r.discipline}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{r.type}</Badge>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {data && (
        <Pagination
          page={data.meta.page}
          totalPages={data.meta.total_pages}
          onPageChange={(p) => updateSearch({ page: p })}
        />
      )}
    </div>
  )
}

// 移动端筛选：默认收起，点击"筛选"展开。与桌面常驻筛选卡片是不同的交互形态。
function MobileFilters({
  search,
  updateSearch,
}: {
  search: CatalogSearch
  updateSearch: (patch: Partial<CatalogSearch>) => void
}) {
  const [open, setOpen] = useState(false)
  const activeCount = [
    search.q,
    search.type,
    search.discipline,
    search.year,
  ].filter(Boolean).length

  return (
    <div className="mb-4">
      <Button
        type="button"
        variant="outline"
        className="w-full justify-between"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4" />
          筛选
          {activeCount > 0 && (
            <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
              {activeCount}
            </span>
          )}
        </span>
        <span className="text-xs text-muted-foreground">{open ? '收起' : '展开'}</span>
      </Button>

      {open && (
        <div className="mt-3 space-y-3 rounded-lg border bg-muted/30 p-3">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">搜索</label>
            <Input
              placeholder="标题/作者/摘要"
              defaultValue={search.q ?? ''}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  updateSearch({ q: (e.target as HTMLInputElement).value, page: 1 })
                }
              }}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">类型</label>
            <Select
              value={search.type ?? 'all'}
              onValueChange={(v) =>
                updateSearch({
                  type: v === 'all' ? undefined : (v as ResourceType),
                  page: 1,
                })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">学科</label>
            <Input
              placeholder="如 computer science"
              defaultValue={search.discipline ?? ''}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  updateSearch({
                    discipline: (e.target as HTMLInputElement).value,
                    page: 1,
                  })
                }
              }}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">年份</label>
            <Input
              type="number"
              placeholder="如 2024"
              defaultValue={search.year ?? ''}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const v = (e.target as HTMLInputElement).value
                  updateSearch({ year: v ? Number(v) : undefined, page: 1 })
                }
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
