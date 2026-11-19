import type { TextareaHTMLAttributes } from 'react'
import { forwardRef, useId } from 'react'

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  name: string
  label: string
  error?: string
}

/** Same wiring as `FormField` (label, error linked with `aria-describedby`) for multi-line text. */
export const TextAreaField = forwardRef<HTMLTextAreaElement, TextAreaFieldProps>(
  function TextAreaField({ name, label, error, className = '', ...rest }, ref) {
    const id = useId()
    const errorId = `${id}-error`

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="text-sm font-medium text-slate-800">
          {label}
        </label>
        <textarea
          id={id}
          ref={ref}
          name={name}
          rows={3}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={`w-full rounded-md border border-slate-300 px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 aria-[invalid=true]:border-red-600 ${className}`}
          {...rest}
        />
        {error ? (
          <p id={errorId} role="alert" className="text-xs text-red-700">
            {error}
          </p>
        ) : null}
      </div>
    )
  },
)
