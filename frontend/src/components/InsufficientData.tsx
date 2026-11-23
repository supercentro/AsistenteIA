import { strings } from '../lib/strings.es'

/** A figure the API withheld: it is never drawn as zero and never gets a bar. */
export function InsufficientData() {
  return <span className="text-slate-600 italic">{strings.activity.insufficient}</span>
}
