import { useState } from 'react'
import { Check, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { useResources, useUpdateResource } from '@/hooks/api/use-modules'
import type { ResourceResponse } from '@/lib/types'
import { extractError } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface RowProps {
  resource: ResourceResponse
  onSaved: () => void
}

function VolumeIssueRow({ resource, onSaved }: RowProps) {
  const update = useUpdateResource()
  const [volume, setVolume] = useState(resource.volume ?? '')
  const [issue, setIssue] = useState(resource.issue ?? '')

  const dirty = volume !== (resource.volume ?? '') || issue !== (resource.issue ?? '')

  const save = async () => {
    try {
      await update.mutateAsync({
        id: resource.id,
        body: {
          volume: volume || null,
          issue: issue || null,
        },
      })
      toast.success(`#${resource.id} 卷/期已保存`)
      onSaved()
    } catch (err) {
      toast.error(extractError(err, '保存失败'))
    }
  }

  return (
    <TableRow key={resource.id}>
      <TableCell className="font-mono text-xs text-muted-foreground">{resource.id}</TableCell>
      <TableCell className="max-w-64 truncate text-sm">{resource.title}</TableCell>
      <TableCell>
        <Input value={volume} onChange={(e) => setVolume(e.target.value)} placeholder="—" />
      </TableCell>
      <TableCell>
        <Input value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="—" />
      </TableCell>
      <TableCell>
        {dirty ? (
          <Button size="sm" onClick={() => void save()} disabled={update.isPending}>
            <Check className="h-4 w-4" />
            保存
          </Button>
        ) : (
          <Pencil className="h-4 w-4 text-muted-foreground/40" />
        )}
      </TableCell>
    </TableRow>
  )
}

/**
 * Write-side volume/issue management: edit the `volume` / `issue` fields
 * of catalog resources directly from the admin area (PATCH /catalog/{id}).
 * The read-side aggregation on /admin/volumes and /admin/issues picks the
 * changes up automatically.
 */
export function VolumeIssueEditor() {
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useResources({ page_size: 100 })
  const [revision, setRevision] = useState(0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">资源卷/期编辑</CardTitle>
        <CardDescription>
          直接修改目录资源的卷号（volume）与期号（issue）。卷/期列表页按此数据
          自动聚合；留空保存即清空该字段。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">加载中…</p>
        ) : isError ? (
          <div className="flex items-center justify-between text-sm">
            <span className="text-destructive">加载失败</span>
            <Button size="sm" variant="outline" onClick={() => void refetch()}>
              重试
            </Button>
          </div>
        ) : (data?.data.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">目录中暂无资源。</p>
        ) : (
          <div className="max-h-96 overflow-y-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-14">ID</TableHead>
                  <TableHead>标题</TableHead>
                  <TableHead className="w-28">卷号</TableHead>
                  <TableHead className="w-28">期号</TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data!.data.map((r) => (
                  <VolumeIssueRow
                    key={`${dataUpdatedAt}-${revision}-${r.id}`}
                    resource={r}
                    onSaved={() => {
                      setRevision((v) => v + 1)
                      void refetch()
                    }}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
