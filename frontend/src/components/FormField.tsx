import type { InputHTMLAttributes } from 'react'
import { forwardRef, useId } from 'react'

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  name: string
  label: string
  hint?: string
  error?: string
}

/** Label, input, hint and error wired together; compatible with React Hook Form's `register`. */
export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(function FormField(
  { name, label, hint, error, className = '', ...rest },
  ref,
) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-800">
        {label}
      </label>
      <input
        id={id}
        ref={ref}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={`min-h-11 w-full rounded-md border border-slate-300 px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 aria-[invalid=true]:border-red-600 read-only:bg-slate-100 ${className}`}
        {...rest}
      />
      {hint ? (
        <p id={hintId} className="text-xs text-slate-600">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-red-700">
          {error}
        </p>
      ) : null}
    </div>
  )
})
