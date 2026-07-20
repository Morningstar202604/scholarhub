import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { AxiosError } from 'axios'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
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
