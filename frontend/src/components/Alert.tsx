import type { ReactNode } from 'react'

type AlertVariant = 'error' | 'success' | 'info'

interface AlertProps {
  variant: AlertVariant
  children: ReactNode
}

const STYLES: Record<AlertVariant, string> = {
  error: 'border-red-300 bg-red-50 text-red-900',
  success: 'border-green-300 bg-green-50 text-green-900',
  info: 'border-sky-300 bg-sky-50 text-sky-900',
}

/** Content is always rendered as React text, never as markup. */
export function Alert({ variant, children }: AlertProps) {
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={`break-words rounded-md border px-4 py-3 text-sm ${STYLES[variant]}`}
    >
      {children}
    </div>
  )
}
