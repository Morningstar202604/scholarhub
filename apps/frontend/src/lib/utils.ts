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
