import { useState } from 'react'
import { Plus, Check } from 'lucide-react'
import { toast } from 'sonner'
import {
  useAddReadingListItem,
  useCreateReadingList,
  useReadingLists,
} from '@/hooks/api/use-modules'
import { extractError } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

interface AddToReadingListProps {
  resourceId: number
  /** Trigger node, e.g. <Button variant="outline">…</Button> */
  trigger: React.ReactNode
}

/**
 * Pick one of the user's reading lists (or create a new one) and add the
 * given resource to it. Wraps the library module's existing API
 * (POST /reading-lists/{id}/items is idempotent) in a small dialog.
 */
export function AddToReadingList({ resourceId, trigger }: AddToReadingListProps) {
  const [open, setOpen] = useState(false)
  const [newName, setNewName] = useState('')

  const lists = useReadingLists(1, 50)
  const add = useAddReadingListItem()
  const createList = useCreateReadingList()

  const addToList = async (listId: number, close = false) => {
    try {
      await add.mutateAsync({ listId, body: { resource_id: resourceId } })
      toast.success('已加入阅读列表')
      if (close) setOpen(false)
    } catch (err) {
      toast.error(extractError(err, '加入失败'))
    }
  }

  const onCreateAndAdd = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      const created = await createList.mutateAsync({ name })
      setNewName('')
      await add.mutateAsync({ listId: created.id, body: { resource_id: resourceId } })
      toast.success(`已创建「${name}」并加入`)
      setOpen(false)
    } catch (err) {
      toast.error(extractError(err, '创建失败'))
    }
  }

  return (
    <>
      <span className="block" onClick={() => setOpen(true)}>
        {trigger}
      </span>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>加入阅读列表</DialogTitle>
          </DialogHeader>

          {lists.isLoading ? (
            <p className="text-sm text-muted-foreground">加载中…</p>
          ) : (lists.data?.data ?? []).length > 0 ? (
            <div className="max-h-56 space-y-1 overflow-y-auto">
              {(lists.data?.data ?? []).map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => addToList(l.id, true)}
                  disabled={add.isPending}
                  className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50"
                >
                  <span className="truncate">{l.name}</span>
                  <Plus className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">还没有阅读列表，先创建一个。</p>
          )}

          <div className="flex gap-2 border-t pt-3">
            <Input
              placeholder="新建列表名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void onCreateAndAdd()
              }}
            />
            <Button
              onClick={() => void onCreateAndAdd()}
              disabled={!newName.trim() || createList.isPending || add.isPending}
            >
              <Check className="h-4 w-4" />
              创建
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

