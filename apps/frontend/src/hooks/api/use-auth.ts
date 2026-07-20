import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import type {
  ForgotPasswordRequest,
  MessageResponse,
  ResetPasswordRequest,
  ResendVerificationRequest,
  TokenResponse,
  UserCreate,
  UserLogin,
  UserResponse,
  VerifyEmailRequest,
} from '@/lib/types'

export const AUTH_KEY = ['auth'] as const

// 登录后拉一次 /auth/me 拿完整 user（含 is_email_verified）
export function useMe() {
  return useQuery<UserResponse>({
    queryKey: [...AUTH_KEY, 'me'],
    queryFn: async () => (await api.get<UserResponse>('/auth/me')).data,
    enabled: !!useAuthStore.getState().token,
    staleTime: 60_000,
  })
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth)
  const qc = useQueryClient()
  return useMutation<TokenResponse, Error, UserLogin>({
    mutationFn: async (body) => (await api.post<TokenResponse>('/auth/login', body)).data,
    onSuccess: (data) => {
      setAuth(data.access_token, {
        id: data.user_id,
        username: data.username,
        is_admin: data.is_admin,
      })
      void qc.invalidateQueries({ queryKey: [...AUTH_KEY, 'me'] })
    },
  })
}

export function useRegister() {
  const setAuth = useAuthStore((s) => s.setAuth)
  const qc = useQueryClient()
  return useMutation<TokenResponse, Error, UserCreate>({
    mutationFn: async (body) => (await api.post<TokenResponse>('/auth/register', body)).data,
    onSuccess: (data) => {
      setAuth(data.access_token, {
        id: data.user_id,
        username: data.username,
        is_admin: data.is_admin,
      })
      void qc.invalidateQueries({ queryKey: [...AUTH_KEY, 'me'] })
    },
  })
}

export function useLogout() {
  const logout = useAuthStore((s) => s.logout)
  const qc = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      await api.post('/auth/logout')
    },
    onSettled: () => {
      logout()
      // 清空所有缓存，避免上一个用户的数据残留
      void qc.clear()
    },
  })
}

export function useVerifyEmail() {
  return useMutation<MessageResponse, Error, VerifyEmailRequest>({
    mutationFn: async (body) =>
      (await api.post<MessageResponse>('/auth/verify-email', body)).data,
  })
}

export function useResendVerification() {
  return useMutation<MessageResponse, Error, ResendVerificationRequest>({
    mutationFn: async (body) =>
      (await api.post<MessageResponse>('/auth/resend-verification', body)).data,
  })
}

export function useForgotPassword() {
  return useMutation<MessageResponse, Error, ForgotPasswordRequest>({
    mutationFn: async (body) =>
      (await api.post<MessageResponse>('/auth/forgot-password', body)).data,
  })
}

export function useResetPassword() {
  return useMutation<MessageResponse, Error, ResetPasswordRequest>({
    mutationFn: async (body) =>
      (await api.post<MessageResponse>('/auth/reset-password', body)).data,
  })
}

// 改密 + 改资料（走 /users/me）
export function useUpdateMe() {
  const qc = useQueryClient()
  return useMutation<UserResponse, Error, Partial<UserResponse>>({
    mutationFn: async (body) => (await api.patch<UserResponse>('/users/me', body)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...AUTH_KEY, 'me'] })
    },
  })
}

export function useChangePassword() {
  return useMutation<void, Error, { oldPassword: string; newPassword: string }>({
    mutationFn: async ({ oldPassword, newPassword }) => {
      await api.post('/users/me/password', {
        old_password: oldPassword,
        new_password: newPassword,
      })
    },
  })
}
