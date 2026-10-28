import { strings } from '../lib/strings.es'
import { Button } from './Button'

interface ErrorStateProps {
  message: string
  onRetry: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-md border border-red-300 bg-red-50 p-4 text-red-900"
    >
      <p className="break-words">{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        {strings.states.retry}
      </Button>
    </div>
  )
}
