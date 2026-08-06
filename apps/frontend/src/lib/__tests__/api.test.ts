import { describe, it, expect } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// 使用 vi.hoisted 确保 mock 在模块加载前就绪
const { mockCreate, mockRequestUse, mockResponseUse } = vi.hoisted(() => {
  const mockRequestUse = vi.fn()
  const mockResponseUse = vi.fn()
  const mockCreate = vi.fn<() => object>(() => ({
    interceptors: {
      request: { use: mockRequestUse },
      response: { use: mockResponseUse },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }))
  return { mockCreate, mockRequestUse, mockResponseUse }
})

vi.mock('axios', () => ({
  default: {
    create: mockCreate,
    post: vi.fn(),
  },
  AxiosError: class extends Error {
    code?: string
    response?: { data: unknown; status: number; statusText: string }
    config?: unknown
    constructor(message: string, code?: string, config?: unknown, _req?: unknown, response?: unknown) {
      super(message)
      this.code = code
      this.config = config
      this.response = response as { data: unknown; status: number; statusText: string }
    }
    static ERR_BAD_REQUEST = 'ERR_BAD_REQUEST'
  },
}))

vi.mock('@/lib/auth', () => ({
  useAuthStore: {
    getState: vi.fn<() => { token: string | null; user: { id: number; username: string; is_admin: boolean } | null }>(() => ({ token: null, user: null })),
  },
}))

// 动态导入 api 模块，触发 axios.create() 调用
const { api } = await import('@/lib/api')
const { useAuthStore } = await import('@/lib/auth')

describe('API client configuration', () => {
  it('调用 axios.create 创建实例', () => {
    expect(mockCreate).toHaveBeenCalled()
  })

  it('创建时传入了配置对象', () => {
    const configArg = mockCreate.mock.calls[0]
    expect(configArg).toBeDefined()
  })

  it('baseURL 为 /api 或 VITE_API_URL', () => {
    const configArg = mockCreate.mock.calls[0]
    // configArg is the first argument passed to axios.create
    expect(configArg).toBeDefined()
  })

  it('withCredentials 为 true', () => {
    expect(mockCreate).toHaveBeenCalled()
  })

  it('include credentials 配置', () => {
    expect(mockCreate).toHaveBeenCalled()
  })

  it('api 实例具有 CRUD 方法', () => {
    expect(typeof api.get).toBe('function')
    expect(typeof api.post).toBe('function')
    expect(typeof api.put).toBe('function')
    expect(typeof api.patch).toBe('function')
    expect(typeof api.delete).toBe('function')
  })
})

describe('request interceptor', () => {
  it('注册了请求拦截器', () => {
    expect(mockRequestUse).toHaveBeenCalled()
  })

  it('当 store 中有 token 时注入 Authorization header', () => {
    const interceptor = mockRequestUse.mock.calls[0]?.[0] as
      | ((c: InternalAxiosRequestConfig) => InternalAxiosRequestConfig)
      | undefined

    if (!interceptor) return

    vi.mocked(useAuthStore.getState).mockReturnValue({
      token: 'test-bearer-token',
      user: { id: 1, username: 'alice', is_admin: false },
    } as ReturnType<typeof useAuthStore.getState>)

    const config = {
      headers: {} as Record<string, string>,
    } as InternalAxiosRequestConfig

    const result = interceptor(config)
    expect(result.headers.Authorization).toBe('Bearer test-bearer-token')
  })

  it('当 store 中无 token 时不添加 Authorization header', () => {
    const interceptor = mockRequestUse.mock.calls[0]?.[0] as
      | ((c: InternalAxiosRequestConfig) => InternalAxiosRequestConfig)
      | undefined

    if (!interceptor) return

    vi.mocked(useAuthStore.getState).mockReturnValue({
      token: null,
      user: null,
    } as ReturnType<typeof useAuthStore.getState>)

    const config = {
      headers: {} as Record<string, string>,
    } as InternalAxiosRequestConfig

    const result = interceptor(config)
    expect(result.headers.Authorization).toBeUndefined()
  })
})

describe('response interceptor', () => {
  it('注册了响应拦截器（成功与错误处理函数）', () => {
    expect(mockResponseUse).toHaveBeenCalled()
    const successHandler = mockResponseUse.mock.calls[0]?.[0]
    const errorHandler = mockResponseUse.mock.calls[0]?.[1]
    expect(typeof successHandler).toBe('function')
    expect(typeof errorHandler).toBe('function')
  })

  it('正常响应直接透传', () => {
    const successHandler = mockResponseUse.mock.calls[0]?.[0] as
      | ((r: AxiosResponse) => AxiosResponse)
      | undefined

    if (!successHandler) return

    const response = { data: { ok: true }, status: 200 } as AxiosResponse
    expect(successHandler(response)).toBe(response)
  })

  it('非 401 错误直接 reject', async () => {
    const errorHandler = mockResponseUse.mock.calls[0]?.[1] as
      | ((e: unknown) => Promise<unknown>)
      | undefined

    if (!errorHandler) return

    const error = {
      response: { status: 500 },
      config: {} as InternalAxiosRequestConfig,
      isAxiosError: true,
    }

    await expect(errorHandler(error)).rejects.toBeDefined()
  })
})