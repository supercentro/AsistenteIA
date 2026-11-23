import { strings } from '../lib/strings.es'

interface PrivacyNoteProps {
  minimumGroup: number
}

export function PrivacyNote({ minimumGroup }: PrivacyNoteProps) {
  return (
    <p className="rounded-md border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
      {strings.activity.note(minimumGroup)}
    </p>
  )
}
