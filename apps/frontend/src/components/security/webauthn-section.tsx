import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Fingerprint, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  webAuthnCredentialDelete,
  webAuthnCredentialsList,
  webAuthnRegisterBegin,
  webAuthnRegisterComplete,
} from '@/lib/webauthn'
import type { WebAuthnCredentialInfo } from '@/lib/webauthn'
import { extractError } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const QUERY_KEY = ['webauthn', 'credentials'] as const

export function useWebAuthnCredentials(enabled = true) {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: webAuthnCredentialsList,
    enabled,
    staleTime: 60_000,
  })
}

export function WebAuthnSection() {
  const qc = useQueryClient()
  const creds = useWebAuthnCredentials()
  const [registering, setRegistering] = useState(false)

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: QUERY_KEY })
  }

  const startRegister = async () => {
    if (!('credentials' in navigator) || !window.PublicKeyCredential) {
      toast.error('当前浏览器不支持 Passkey / WebAuthn')
      return
    }
    setRegistering(true)
    try {
      const options = await webAuthnRegisterBegin()
      const credential = (await navigator.credentials.create({
        publicKey: options as unknown as PublicKeyCredentialCreationOptions,
      })) as PublicKeyCredential | null
      if (!credential) {
        toast.error('Passkey 注册被取消')
        return
      }
      const name = window.prompt('给这个 Passkey 起个名字（如「Mac Touch ID」）', 'Passkey') ?? 'Passkey'
      const created = await webAuthnRegisterComplete(credential, name)
      toast.success(`Passkey「${created.name}」已添加`)
      invalidate()
    } catch (err) {
      toast.error(extractError(err, 'Passkey 注册失败'))
    } finally {
      setRegistering(false)
    }
  }

  const remove = async (cred: WebAuthnCredentialInfo) => {
    try {
      await webAuthnCredentialDelete(cred.id)
      toast.success('已删除')
      invalidate()
    } catch (err) {
      toast.error(extractError(err, '删除失败'))
    }
  }

  const supported = typeof navigator !== 'undefined' && 'credentials' in navigator

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Fingerprint className="h-5 w-5" />
          Passkey（WebAuthn）
          <Badge variant="outline">
            {(creds.data?.length ?? 0) > 0 ? `已注册 ${creds.data?.length}` : '未注册'}
          </Badge>
        </CardTitle>
        <CardDescription>
          用设备指纹 / 平台 Passkey 代替 TOTP 动态码完成登录，支持 Face ID、
          Touch ID、Windows Hello。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!supported ? (
          <p className="text-sm text-muted-foreground">
            当前浏览器不支持 WebAuthn。
          </p>
        ) : creds.isLoading ? (
          <p className="text-sm text-muted-foreground">加载中…</p>
        ) : (creds.data?.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">
            还没有 Passkey。注册后，登录页即可用它一步完成登录。
          </p>
        ) : (
          <ul className="space-y-2">
            {(creds.data ?? []).map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{c.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {c.transports.length > 0
                      ? c.transports.join(' · ')
                      : '传输方式未知'}
                    {c.created_at ? ` · 添加于 ${new Date(c.created_at).toLocaleDateString()}` : ''}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void remove(c)}
                  data-testid={`delete-passkey-${c.id}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <Button variant="outline" onClick={() => void startRegister()} disabled={registering}>
          <Plus className="h-4 w-4" />
          {registering ? '注册中…' : '注册新 Passkey'}
        </Button>
      </CardContent>
    </Card>
  )
}
