import { api } from '@/lib/api'
import type { TokenResponse } from './types'

// The backend serialises WebAuthn options as unpadded base64url (the
// `webauthn` library default). Browsers expect standard base64 for
// options, and return unpadded base64url for the credential payloads.
// These two helpers convert at the boundary so the UI code can stay
// plain.

export function b64urlToB64(input: string): string {
  let b = input.replace(/-/g, '+').replace(/_/g, '/')
  while (b.length % 4 !== 0) b += '='
  return b
}

export function bufferToB64url(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export interface WebAuthnCredentialInfo {
  id: string
  name: string
  created_at: string
  transports: string[]
}

interface CredentialBody {
  id: string
  rawId: string
  type?: string
  response: Record<string, unknown>
}

function toCredentialBody(cred: PublicKeyCredential): CredentialBody {
  const response = cred.response as unknown as Record<string, unknown>
  const body: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(response)) {
    if (v instanceof ArrayBuffer || v instanceof Uint8Array) body[k] = bufferToB64url(v)
    else body[k] = v
  }
  return {
    id: cred.id,
    rawId: bufferToB64url(cred.rawId),
    type: 'public-key',
    response: body,
  }
}

function fixupOptions(options: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...options }
  if (out.challenge) out.challenge = b64urlToB64(out.challenge as string)
  if (out.user && typeof out.user === 'object') {
    out.user = { ...(out.user as object), id: b64urlToB64((out.user as { id: string }).id) }
  }
  const allow = out.allowCredentials as { id: string }[] | undefined
  if (Array.isArray(allow)) {
    out.allowCredentials = allow.map((c) => ({ ...c, id: b64urlToB64(c.id) }))
  }
  return out
}

export async function webAuthnRegisterBegin(): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/auth/webauthn/register/begin', {})
  return fixupOptions(data)
}

export async function webAuthnRegisterComplete(
  credential: PublicKeyCredential,
  name: string,
): Promise<WebAuthnCredentialInfo> {
  const { data } = await api.post<WebAuthnCredentialInfo>(
    '/auth/webauthn/register/complete',
    { credential: toCredentialBody(credential), name },
  )
  return data
}

export async function webAuthnAuthenticateBegin(
  username: string,
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(
    '/auth/webauthn/authenticate/begin',
    { username },
  )
  return fixupOptions(data)
}

export async function webAuthnAuthenticateComplete(
  username: string,
  credential: PublicKeyCredential,
): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/webauthn/authenticate/complete', {
    username,
    credential: toCredentialBody(credential),
  })
  return data
}

export async function webAuthnCredentialsList(): Promise<WebAuthnCredentialInfo[]> {
  const { data } = await api.get<{ credentials: WebAuthnCredentialInfo[] }>(
    '/auth/webauthn/credentials',
  )
  return data.credentials
}

export async function webAuthnCredentialDelete(id: string): Promise<void> {
  await api.delete(`/auth/webauthn/credentials/${encodeURIComponent(id)}`)
}
