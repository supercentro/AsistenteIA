import { barWidth, formatDay } from '../lib/activityFormat'
import { strings } from '../lib/strings.es'
import type { ActivityResponse } from '../types/api'
import { InsufficientData } from './InsufficientData'

const text = strings.activity

interface WeeklyQuestionsProps {
  weeks: ActivityResponse['questions']
}

/** The weeks as a table; the bar next to a shown count is decorative and hidden from readers. */
export function WeeklyQuestions({ weeks }: WeeklyQuestionsProps) {
  const maximum = Math.max(0, ...weeks.map((week) => week.count ?? 0))
  return (
    <table className="w-full border-collapse text-left">
      <caption className="mb-2 text-left text-lg font-semibold">{text.weekly.caption}</caption>
      <thead>
        <tr className="border-b border-slate-300 text-sm text-slate-600">
          <th scope="col" className="py-1 pr-4 font-normal">
            {text.weekly.week}
          </th>
          <th scope="col" className="py-1 font-normal">
            {text.weekly.questions}
          </th>
        </tr>
      </thead>
      <tbody>
        {weeks.map((week) => (
          <tr key={week.period_start} className="border-b border-slate-200">
            <td className="py-2 pr-4">{formatDay(week.period_start)}</td>
            <td className="py-2">
              {week.count === null ? (
                <InsufficientData />
              ) : (
                <span className="flex items-center gap-3">
                  <span className="w-10 tabular-nums">{week.count}</span>
                  <span aria-hidden="true" className="block h-2 flex-1 rounded bg-slate-200">
                    <span
                      data-bar
                      aria-hidden="true"
                      className="block h-2 rounded bg-slate-700"
                      style={{ width: barWidth(week.count, maximum) }}
                    />
                  </span>
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
