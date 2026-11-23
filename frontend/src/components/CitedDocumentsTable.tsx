import { strings } from '../lib/strings.es'
import type { ActivityResponse } from '../types/api'
import { InsufficientData } from './InsufficientData'

const text = strings.activity

interface CitedDocumentsTableProps {
  documents: ActivityResponse['documents']
}

/** Citation counts per document; the file name is plain text and the identifier is not shown. */
export function CitedDocumentsTable({ documents }: CitedDocumentsTableProps) {
  return (
    <div className="flex flex-col gap-2">
      <table className="w-full border-collapse text-left">
        <caption className="mb-2 text-left text-lg font-semibold">{text.documents.caption}</caption>
        <thead>
          <tr className="border-b border-slate-300 text-sm text-slate-600">
            <th scope="col" className="py-1 pr-4 font-normal">
              {text.documents.name}
            </th>
            <th scope="col" className="py-1 font-normal">
              {text.documents.cited}
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document, index) => (
            <tr
              key={`${document.document_id ?? 'deleted'}-${index}`}
              className="border-b border-slate-200"
            >
              <td className="break-all py-2 pr-4">
                <bdi>{document.filename}</bdi>
              </td>
              <td className="py-2 tabular-nums">
                {document.cited_appearances === null ? (
                  <InsufficientData />
                ) : (
                  document.cited_appearances
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-sm text-slate-600">{text.documents.note}</p>
    </div>
  )
}
