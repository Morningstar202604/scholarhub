import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { AxiosError } from 'axios'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 后端返回的时间是原始 ISO 字符串（如 `2026-09-14T14:21:51.181237Z`），
 * 直接渲染既难读又会撑破卡片布局，统一格式化后再展示。
 * 空值 / 非法值回退到 fallback，避免页面出现 "Invalid Date"。
 */
export function formatDateTime(iso: string | null | undefined, fallback = '—'): string {
  if (!iso) return fallback
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleString()
}

// Single source of truth for converting a thrown value (axios + unknown)
// into a user-facing toast message. Used by every mutation catch block.
export function extractError(err: unknown, fallback: string): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
  }
  return fallback
}

// Parse a comma-separated list field (authors / tags / keywords / jel_codes)
// into a trimmed, empty-filtered string array. Replaces the repeated inline
// `.split(',').map(s => s.trim()).filter(Boolean)` pattern across the app.
export function parseListField(s: string): string[] {
  return s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
}

// Trigger a browser download from a Blob response (export / file download).
// Filename is parsed from Content-Disposition, falling back to fallbackName.
// Deduplicates the blob-download logic previously hand-rolled in
// exportResources() and downloadSubmissionFile().
export function downloadBlob(data: Blob, disposition: string, fallbackName: string): void {
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const filename = match?.[1] ?? fallbackName
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Backend list endpoints return a bare array with no meta; the total page
// count is inferred from whether the current page came back full. Extracted
// from the identical logic in admin/users.tsx and admin/audit-logs.tsx.
export function inferTotalPagesFromFullPage(
  items: unknown[],
  pageSize: number,
  page: number,
): number {
  return items.length >= pageSize ? page + 1 : page
}
