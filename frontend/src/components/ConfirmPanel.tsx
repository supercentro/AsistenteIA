import { useEffect, useRef, useState } from 'react'
import { Button } from './Button'

interface ConfirmPanelProps {
  /** Unique within the page: names the question for assistive technology. */
  id: string
  triggerLabel: string
  question: string
  body: string
  confirmLabel: string
  workingLabel: string
  cancelLabel: string
  /** The action of this very item is in flight. */
  pending: boolean
  /** Some action of the list is in flight: no confirm control may be used meanwhile. */
  busy: boolean
  onConfirm: () => void
}

/**
 * Inline confirmation shared by the lists: a trigger that becomes a group with the question, a
 * body and confirm and cancel controls. The focus goes into the group and, on cancel, back to the
 * trigger. No modal and no dependency.
 */
export function ConfirmPanel({
  id,
  triggerLabel,
  question,
  body,
  confirmLabel,
  workingLabel,
  cancelLabel,
  pending,
  busy,
  onConfirm,
}: ConfirmPanelProps) {
  const [confirming, setConfirming] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  useEffect(() => {
    if (confirming) {
      panelRef.current?.focus()
    } else if (returnFocus.current) {
      returnFocus.current = false
      triggerRef.current?.focus()
    }
  }, [confirming])

  function cancel() {
    returnFocus.current = true
    setConfirming(false)
  }

  if (!confirming) {
    return (
      <div>
        <Button
          ref={triggerRef}
          variant="secondary"
          className="max-w-full text-left [overflow-wrap:anywhere]"
          onClick={() => setConfirming(true)}
        >
          {triggerLabel}
        </Button>
      </div>
    )
  }

  const questionId = `confirm-${id}`
  return (
    <div
      ref={panelRef}
      role="group"
      aria-labelledby={questionId}
      tabIndex={-1}
      className="flex flex-col gap-2 rounded-md border border-red-300 bg-red-50 p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
    >
      <p id={questionId} className="break-words font-medium text-red-900 [unicode-bidi:isolate]">
        {question}
      </p>
      <p className="text-sm text-red-900">{body}</p>
      <div className="flex flex-wrap gap-2">
        <Button pending={pending} disabled={busy} onClick={onConfirm}>
          {pending ? workingLabel : confirmLabel}
        </Button>
        <Button variant="secondary" disabled={pending} onClick={cancel}>
          {cancelLabel}
        </Button>
      </div>
    </div>
  )
}
