import { Link, useParams } from 'react-router-dom'
import { ErrorState } from '../components/ErrorState'
import { InsufficientData } from '../components/InsufficientData'
import { LoadingState } from '../components/LoadingState'
import { TopicRanking } from '../components/TopicRanking'
import { TopicsNotAvailable } from '../components/TopicsNotAvailable'
import { useFocusOnMount } from '../hooks/useFocusOnMount'
import { useSession } from '../hooks/useSession'
import { useTopicRanking } from '../hooks/useTopics'
import { formatDay } from '../lib/activityFormat'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { TopicRankingResponse } from '../types/api'
import ForbiddenPage from './ForbiddenPage'

const text = strings.topics.ranking

export default function TeacherTopicsPage() {
  const { subjectId = '' } = useParams()
  return <Content key={subjectId} subjectId={subjectId} />
}

function Content({ subjectId }: { subjectId: string }) {
  const { user } = useSession()
  const query = useTopicRanking(user?.id ?? '', subjectId)
  const error = query.error instanceof ApiError ? query.error : null

  if (error?.status === 403) return <ForbiddenPage />
  if (error?.status === 404 || error?.status === 422) return <TopicsNotAvailable />
  if (query.isPending || error?.status === 401) return <LoadingState label={text.loading} />
  if (query.data === undefined) {
    return (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void query.refetch()}
      />
    )
  }
  return <Loaded subjectId={subjectId} data={query.data} />
}

function Figures({ data }: { data: TopicRankingResponse }) {
  if (data.topics_defined === 0) {
    return <p className="rounded-md border border-slate-300 bg-white p-4">{text.noTopics}</p>
  }
  if (data.window.weeks === 0) {
    return (
      <p role="status" className="rounded-md border border-slate-300 bg-white p-4">
        {strings.activity.noWeeks}
      </p>
    )
  }
  if (data.topics.length === 0) {
    return (
      <div role="status" className="rounded-md border border-slate-300 bg-white p-4">
        <p className="font-medium">
          <InsufficientData />
        </p>
        <p className="text-sm text-slate-600">{text.nothingToShow}</p>
      </div>
    )
  }
  return <TopicRanking topics={data.topics} />
}

function Loaded({ subjectId, data }: { subjectId: string; data: TopicRankingResponse }) {
  const heading = useFocusOnMount<HTMLHeadingElement>()
  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm text-slate-900 underline" to={`/subjects/${subjectId}/activity`}>
        {text.back}
      </Link>
      <h1 ref={heading} tabIndex={-1} className="text-2xl font-bold">
        {text.title}
      </h1>
      {data.window.weeks > 0 ? (
        <p className="text-slate-600">
          {strings.activity.window(formatDay(data.window.start), formatDay(data.window.end))}
        </p>
      ) : null}
      <Figures data={data} />
      {data.restarted_documents.length > 0 ? (
        <section aria-labelledby="topics-restarted" className="flex flex-col gap-2">
          <h2 id="topics-restarted" className="text-lg font-semibold">
            {text.restartedHeading}
          </h2>
          <ul className="flex flex-col gap-1 text-sm [overflow-wrap:anywhere]">
            {data.restarted_documents.map((item) => (
              <li key={item.document_id}>
                {text.restartedItem(item.filename, formatDay(item.counting_from))}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {data.documents_without_topics.length > 0 ? (
        <section aria-labelledby="topics-without" className="flex flex-col gap-2">
          <h2 id="topics-without" className="text-lg font-semibold">
            {text.withoutHeading}
          </h2>
          <ul className="flex flex-col gap-2 text-sm [overflow-wrap:anywhere]">
            {data.documents_without_topics.map((item) => (
              <li key={item.document_id} className="flex flex-col">
                <bdi className="font-medium">{item.filename}</bdi>
                <span className="text-slate-600">{text.reasons[item.reason]}</span>
                {item.reason === 'not_defined' ? (
                  <Link
                    className="text-slate-900 underline"
                    to={`/subjects/${subjectId}/documents/${item.document_id}/topics`}
                  >
                    {text.define(item.filename)}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="text-sm text-slate-600">{text.note(data.minimum_group)}</p>
    </div>
  )
}
