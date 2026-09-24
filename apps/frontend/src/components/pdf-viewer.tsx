import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { Loading } from '@/components/common/state'
import { Button } from '@/components/ui/button'

// pdf.js 阅读器：替代 iframe 直接嵌 PDF 的方案。
// iframe 的缺点：无法知道总页数/当前页、进度只能按输入猜测、移动端缩放体验差。
// pdf.js 是 Mozilla 开源的 PDF 渲染库，本地解析渲染、支持按页精确同步进度。
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker

interface PdfViewerProps {
  url: string
  /** 初始页码（从服务端进度恢复时传入，1 基） */
  initialPage?: number
  /** 页码变化回调（翻页/恢复后触发，供父组件同步进度） */
  onPageChange?: (page: number) => void
  /** 文档加载完成回调（报告总页数，父组件可做"已读完"判断） */
  onLoaded?: (totalPages: number) => void
}

export default function PdfViewer({
  url,
  initialPage = 1,
  onPageChange,
  onLoaded,
}: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // docRef 持有加载好的文档对象，卸载时销毁释放内存
  const docRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null)
  const pageNumRef = useRef(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // 渲染竞态守卫：页码快速连点时丢弃过期渲染结果
  const renderTokenRef = useRef(0)

  // 渲染指定页（页码变化时调用；初始加载在 onLoad 后调一次）
  const renderPage = async (num: number, doc: pdfjsLib.PDFDocumentProxy) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const token = ++renderTokenRef.current
    const target = Math.min(Math.max(1, num), doc.numPages)
    pageNumRef.current = target
    setPage(target)
    try {
      const pdfPage = await doc.getPage(target)
      // 按容器宽度自适应（1.5x 保证高清屏清晰），单页纵向布局。
      // pdf.js 各版本 viewBox API 有波动，用 scale=1 视口宽度求基准最稳。
      const base = Math.min(canvas.parentElement?.clientWidth ?? 800, 900)
      const viewport1 = pdfPage.getViewport({ scale: 1 })
      const scale = (base / viewport1.width) * 1.5
      const viewport = pdfPage.getViewport({ scale })
      canvas.width = Math.floor(viewport.width)
      canvas.height = Math.floor(viewport.height)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      // v6 的 RenderParameters 类型在 minor 版本间有漂移，这里用 any 桥接：
      // 运行参数（canvasContext + viewport）自 v3 起从未变化，类型声明跟丢而已。
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await pdfPage.render({ canvasContext: ctx, viewport } as any).promise
      if (token === renderTokenRef.current) {
        onPageChange?.(target)
      }
    } catch {
      // 竞态或渲染错误：不弹错，等待下一次翻页重试
    }
  }

  // 文档加载：只跑一次（url 固定）
  useEffect(() => {
    let disposed = false
    ;(async () => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const task = pdfjsLib.getDocument({ url } as any)
        const doc = await task.promise
        if (disposed) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          void (doc as any).destroy()
          return
        }
        docRef.current = doc
        setTotalPages(doc.numPages)
        setLoading(false)
        onLoaded?.(doc.numPages)
        await renderPage(initialPage, doc)
      } catch {
        if (!disposed) {
          setError('PDF 加载失败（文件可能已损坏或格式不支持）')
          setLoading(false)
        }
      }
    })()
    return () => {
      disposed = true
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      void (docRef.current as any)?.destroy()
      docRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  const goTo = (delta: number) => {
    const doc = docRef.current
    if (!doc) return
    void renderPage(pageNumRef.current + delta, doc)
  }

  if (error) {
    return (
      <div className="flex h-full min-h-[40vh] items-center justify-center rounded-md border p-4 text-sm text-muted-foreground">
        {error}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex h-full min-h-[40vh] items-center justify-center rounded-md border">
        <Loading />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 items-start justify-center overflow-auto rounded-md border bg-muted/30 p-2">
        <canvas ref={canvasRef} className="max-w-full rounded-sm shadow" />
      </div>
      {totalPages > 0 && (
        <div className="flex items-center justify-center gap-2 pt-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            onClick={() => goTo(-1)}
            disabled={page <= 1}
            aria-label="上一页"
          >
            上一页
          </Button>
          <span className="tabular-nums">
            {page} / {totalPages} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => goTo(1)}
            disabled={page >= totalPages}
            aria-label="下一页"
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}
