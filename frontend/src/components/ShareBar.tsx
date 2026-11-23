import { barWidth, formatShare } from '../lib/activityFormat'
import { InsufficientData } from './InsufficientData'

interface ShareBarProps {
  label: string
  note?: string
  share: number | null
}

/** A share of answers: the text carries the value, the bar only repeats it for the eye. */
export function ShareBar({ label, note, share }: ShareBarProps) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-sm text-slate-900">{label}</dt>
      <dd className="flex flex-col gap-1">
        {share === null ? (
          <InsufficientData />
        ) : (
          <>
            <span className="text-lg font-semibold">{formatShare(share)}</span>
            <span aria-hidden="true" className="block h-2 w-full rounded bg-slate-200">
              <span
                data-bar
                aria-hidden="true"
                className="block h-2 rounded bg-slate-700"
                style={{ width: barWidth(share, 1) }}
              />
            </span>
          </>
        )}
        {note ? <span className="text-sm text-slate-600">{note}</span> : null}
      </dd>
    </div>
  )
}
