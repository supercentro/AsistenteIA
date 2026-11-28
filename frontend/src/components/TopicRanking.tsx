import { barWidth, formatDay } from '../lib/activityFormat'
import { strings } from '../lib/strings.es'
import type { TopicRankingResponse } from '../types/api'

const text = strings.topics.ranking

interface TopicRankingProps {
  topics: TopicRankingResponse['topics']
}

/** Horizontal bars, hidden from readers, and the table that says everything they draw. */
export function TopicRanking({ topics }: TopicRankingProps) {
  const maximum = Math.max(0, ...topics.map((topic) => topic.answers))
  return (
    <div className="flex flex-col gap-5">
      <ol aria-hidden="true" className="flex flex-col gap-2">
        {topics.map((topic) => (
          <li key={topic.topic_id} className="flex flex-col gap-1">
            <span className="break-words text-sm">
              <bdi>{topic.title}</bdi>
            </span>
            <span className="flex items-center gap-3">
              <span className="block h-3 flex-1 rounded bg-slate-200">
                <span
                  data-bar
                  className="block h-3 rounded bg-slate-700"
                  style={{ width: barWidth(topic.answers, maximum) }}
                />
              </span>
              <span className="w-10 text-right text-sm tabular-nums">{topic.answers}</span>
            </span>
          </li>
        ))}
      </ol>
      <table className="w-full table-fixed border-collapse text-left text-sm">
        <caption className="mb-2 text-left text-lg font-semibold">{text.caption}</caption>
        <thead>
          <tr className="border-b border-slate-300 text-slate-600">
            <th scope="col" className="py-1 pr-2 font-normal [overflow-wrap:anywhere]">
              {text.topic}
            </th>
            <th scope="col" className="py-1 pr-2 font-normal [overflow-wrap:anywhere]">
              {text.document}
            </th>
            <th scope="col" className="w-24 py-1 font-normal">
              {text.answers}
            </th>
          </tr>
        </thead>
        <tbody>
          {topics.map((topic) => (
            <tr key={topic.topic_id} className="border-b border-slate-200 align-top">
              <th scope="row" className="py-2 pr-2 font-medium [overflow-wrap:anywhere]">
                <bdi>{topic.title}</bdi>
              </th>
              <td className="py-2 pr-2 [overflow-wrap:anywhere]">
                <bdi>{topic.filename}</bdi>
                <span className="block text-slate-600">
                  {text.pages(topic.start_page, topic.end_page)}
                </span>
                <span className="block text-slate-600">
                  {text.since(formatDay(topic.counted_since))}
                </span>
                {topic.also_in.length > 0 ? (
                  <span className="block text-slate-600">
                    <span>{text.alsoIn}</span> <bdi>{topic.also_in.join(', ')}</bdi>
                  </span>
                ) : null}
              </td>
              <td className="py-2 tabular-nums">{topic.answers}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
