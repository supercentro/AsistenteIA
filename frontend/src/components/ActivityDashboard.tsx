import { DEFAULT_WEEKS, formatDay } from '../lib/activityFormat'
import { strings } from '../lib/strings.es'
import type { ActivityResponse } from '../types/api'
import { CitedDocumentsTable } from './CitedDocumentsTable'
import { InsufficientData } from './InsufficientData'
import { MetricCard } from './MetricCard'
import { PrivacyNote } from './PrivacyNote'
import { ShareBar } from './ShareBar'
import { WeeklyQuestions } from './WeeklyQuestions'

const text = strings.activity

interface ActivityDashboardProps {
  data: ActivityResponse
}

/** Shows only what the response holds; nothing is derived, compared or ranked. */
export function ActivityDashboard({ data }: ActivityDashboardProps) {
  const noWeeks = data.window.weeks === 0
  const limited = !noWeeks && data.window.weeks < DEFAULT_WEEKS
  const nothingToShow = noWeeks || data.active_students === null
  return (
    <div className="flex flex-col gap-6">
      {noWeeks ? null : (
        <p className="text-slate-600">
          {text.window(formatDay(data.window.start), formatDay(data.window.end))}
        </p>
      )}
      <p className="text-sm text-slate-600">{text.wholeWeeksOnly}</p>
      {limited ? (
        <p className="rounded-md border border-slate-300 bg-white p-3 text-sm">{text.limited}</p>
      ) : null}
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <MetricCard label={text.cards.enrolled}>{data.enrolled_students}</MetricCard>
        <MetricCard label={text.cards.active}>
          {data.active_students === null ? <InsufficientData /> : data.active_students}
        </MetricCard>
      </dl>
      {noWeeks ? null : <p className="text-sm text-slate-600">{text.cards.activeNote}</p>}
      {nothingToShow ? (
        <p role="status" className="rounded-md border border-slate-300 bg-white p-4">
          {noWeeks ? text.noWeeks : text.allSuppressed}
        </p>
      ) : (
        <>
          <WeeklyQuestions weeks={data.questions} />
          <section aria-labelledby="activity-shares" className="flex flex-col gap-3">
            <h2 id="activity-shares" className="text-lg font-semibold">
              {text.shares.heading}
            </h2>
            <dl className="flex flex-col gap-4">
              <ShareBar label={text.shares.noMaterial} share={data.no_material_rate} />
              <ShareBar
                label={text.shares.noCitedSource}
                note={text.shares.noCitedSourceNote}
                share={data.no_cited_source_rate}
              />
            </dl>
          </section>
          <CitedDocumentsTable documents={data.documents} />
        </>
      )}
      <PrivacyNote minimumGroup={data.minimum_group} />
    </div>
  )
}
