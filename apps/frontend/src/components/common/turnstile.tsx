import { useEffect, useRef, useState } from 'react'

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        siteKey: string,
        opts: {
          callback: (token: string) => void
          'error-callback'?: (code: string) => void
          'expired-callback'?: () => void
        },
      ) => string
      remove: (widgetId: string) => void
    }
  }
}

let scriptPromise: Promise<void> | null = null

function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Turnstile script failed to load'))
    document.head.appendChild(script)
  })
  return scriptPromise
}

interface TurnstileWidgetProps {
  siteKey: string
  onToken: (token: string) => void
}

/**
 * Cloudflare Turnstile widget. Renders nothing when no site key is
 * configured (``VITE_TURNSTILE_SITE_KEY``), so deployments without a
 * CAPTCHA provider keep a clean form. The widget re-renders on
 * expiration so the user gets a fresh token automatically.
 */
export function TurnstileWidget({ siteKey, onToken }: TurnstileWidgetProps) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<string>('')
  const onTokenRef = useRef(onToken)

  useEffect(() => {
    onTokenRef.current = onToken
  }, [onToken])

  useEffect(() => {
    if (!siteKey) return
    let cancelled = false

    loadTurnstileScript()
      .then(() => {
        if (cancelled || !window.turnstile || !containerRef.current) return
        setStatus('ready')
        widgetIdRef.current = window.turnstile.render(containerRef.current, siteKey, {
          callback: (token) => onTokenRef.current(token),
          'error-callback': () => setStatus('error'),
          'expired-callback': () => {
            // re-render to offer a fresh widget
            const ts = window.turnstile
            const el = containerRef.current
            if (!ts || !el) return
            ts.remove(widgetIdRef.current)
            widgetIdRef.current = ts.render(el, siteKey, {
              callback: (token) => onTokenRef.current(token),
              'error-callback': () => setStatus('error'),
            })
          },
        })
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })

    return () => {
      cancelled = true
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current)
        widgetIdRef.current = ''
      }
    }
  }, [siteKey])

  if (!siteKey) return null

  return (
    <div className="space-y-1">
      <div ref={containerRef} data-turnstile-status={status} />
      {status === 'error' && (
        <p className="text-xs text-destructive">人机验证加载失败，请刷新页面重试。</p>
      )}
    </div>
  )
}
