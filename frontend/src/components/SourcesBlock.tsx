import { useId } from 'react'
import { strings } from '../lib/strings.es'
import type { Source, SourceAttribution } from '../types/api'

interface SourcesBlockProps {
  sources: readonly Source[]
  /** Absent or null (an older server): the sources are shown as retrieved material. */
  attribution?: SourceAttribution | null
}

const text = strings.chat.sources

/**
 * The fragments the backend associates with an answer, as it gives them. Sources the answer cited
 * show the marker number of the text; sources that were only retrieved are shown apart and
 * collapsed, with no number. Nothing here says that a source proves or supports a statement
 * (TD-062).
 */
export function SourcesBlock({ sources, attribution = null }: SourcesBlockProps) {
  const labelId = useId()
  if (sources.length === 0) {
    return null
  }
  const cited = attribution === 'cited'
  const list = (
    <ul className="flex flex-col gap-1">
      {sources.map((source, index) => (
        <li key={`${source.rank}-${index}`} className="rounded border border-slate-200 p-2 text-sm">
          <p className="break-words font-medium">
            {cited ? (
              <span className="font-semibold text-slate-700">{text.marker(source.rank)} </span>
            ) : null}
            <bdi>{source.filename}</bdi>
            {source.page_number !== null && source.page_number !== undefined ? (
              <span className="font-normal text-slate-600">
                {' · '}
                {text.page(source.page_number)}
              </span>
            ) : null}
          </p>
          <details>
            <summary className="cursor-pointer text-xs text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900">
              {text.snippet}
            </summary>
            <p className="mt-1 whitespace-pre-wrap break-words text-slate-700">{source.snippet}</p>
          </details>
        </li>
      ))}
    </ul>
  )
  return (
    <div role="group" aria-labelledby={labelId} className="mt-2 flex flex-col gap-1">
      {cited ? (
        <>
          <p id={labelId} className="text-xs font-semibold text-slate-700">
            {text.cited}
          </p>
          {list}
        </>
      ) : (
        <details>
          <summary
            id={labelId}
            className="cursor-pointer text-xs font-semibold text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
          >
            {text.retrieved}
          </summary>
          <div className="mt-1">{list}</div>
        </details>
      )}
      <p className="text-xs text-slate-600">{text.note}</p>
    </div>
  )
}
