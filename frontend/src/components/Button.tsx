import { forwardRef, type ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** A request is in flight: the control is disabled so it cannot be activated twice. */
  pending?: boolean
  variant?: 'primary' | 'secondary'
}

const VARIANTS = {
  primary: 'bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-400',
  secondary:
    'border border-slate-300 bg-white text-slate-900 hover:bg-slate-100 disabled:opacity-60',
} as const

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    pending = false,
    variant = 'primary',
    type = 'button',
    disabled,
    className = '',
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending}
      className={`inline-flex min-h-11 items-center justify-center rounded-md px-4 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-900 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
})
