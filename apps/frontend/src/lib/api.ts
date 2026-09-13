import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from './auth'

// In production, fall back to same-origin /api when VITE_API_URL is not
// injected (avoids shipping a hard-coded localhost URL in the bundle).
// A global timeout keeps a stalled refresh / /auth/me from piling up requests.
const baseURL = import.meta.env.VITE_API_URL ?? '/api'

// 默认 axios 把数组参数序列化成 ids[]=1&ids[]=2（PHP/Rails 风格），
// 但 FastAPI 的 list[int] = Query() 期望 ids=1&ids=2（重复参数风格）。
// 用函数式 paramsSerializer 生成重复参数风格（axios ≥1.4 的推荐写法，
// 替代已弃用的对象式 { indexes: null }）。
const paramsSerializer = (params: Record<string, unknown>): string => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null) search.append(key, String(item))
      }
    } else {
      search.append(key, String(value))
    }
  }
  return search.toString()
}

// Cookie-authenticated endpoints that the backend CSRF middleware
// (double-submit pattern) guards. The backend issues a non-httpOnly
// `csrf` cookie; we echo it back as X-CSRF-Token on these calls.
const CSRF_PROTECTED_PATHS = ['/auth/refresh', '/auth/logout', '/auth/revoke-all']

function readCsrfCookie(): string {
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith('csrf='))
  return match ? decodeURIComponent(match.slice('csrf='.length)) : ''
}

export const api = axios.create({
  baseURL,
  withCredentials: true, // refresh_token lives in an httpOnly cookie; credentials are required
  headers: { 'Content-Type': 'application/json' },
  timeout: 10_000, // global guard against stalled requests piling up
  paramsSerializer,
})

// Inject access_token from the zustand store (read directly, no React coupling).
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // CSRF double-submit for cookie-authenticated state-changing calls.
  const path = config.url ?? ''
  if (config.method?.toLowerCase() !== 'get' && CSRF_PROTECTED_PATHS.some((p) => path.startsWith(p))) {
    const csrf = readCsrfCookie()
    if (csrf) config.headers['X-CSRF-Token'] = csrf
  }
  return config
})

let refreshing: Promise<void> | null = null

// Single-retry 401 handler: exchange the httpOnly refresh_token cookie for a
// new access_token. Concurrent 401s share the same refresh promise so we never
// fire multiple /auth/refresh calls in parallel (which would invalidate each
// other's cookies).
async function refreshOnce(): Promise<void> {
  if (refreshing) return refreshing
  refreshing = (async () => {
    try {
      const csrf = readCsrfCookie()
      const { data } = await axios.post(
        `${baseURL}/auth/refresh`,
        {},
        {
          withCredentials: true,
          timeout: 5_000, // shorter timeout for refresh
          headers: csrf ? { 'X-CSRF-Token': csrf } : undefined,
        },
      )
      useAuthStore.getState().setAuth(data.access_token, {
        id: data.user_id,
        username: data.username,
        is_admin: data.is_admin,
      })
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean
    }

    // Non-401 or already retried: rethrow.
    if (error.response?.status !== 401 || original._retried) {
      return Promise.reject(error)
    }

    // If /auth/refresh itself returns 401, the refresh_token is also dead —
    // clear auth state so the route guard bounces to /login.
    if (original.url?.includes('/auth/refresh')) {
      useAuthStore.getState().logout()
      return Promise.reject(error)
    }

    try {
      await refreshOnce()
      original._retried = true
      return api(original)
    } catch (refreshError) {
      useAuthStore.getState().logout()
      return Promise.reject(refreshError)
    }
  },
)
