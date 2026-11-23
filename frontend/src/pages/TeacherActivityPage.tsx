import { Link, useParams } from 'react-router-dom'
import { ActivityDashboard } from '../components/ActivityDashboard'
import { useFocusOnMount } from '../hooks/useFocusOnMount'
import { ErrorState } from '../components/ErrorState'
import { LoadingState } from '../components/LoadingState'
import { useActivity } from '../hooks/useActivity'
import { useSession } from '../hooks/useSession'
import { ApiError, messageFor } from '../lib/apiError'
import { strings } from '../lib/strings.es'
import type { ActivityResponse } from '../types/api'
import ForbiddenPage from './ForbiddenPage'

const text = strings.activity

/** The same view for another teacher's subject, an unknown one and a capability that is off. */
function NotAvailable() {
  return (
    <section className="flex flex-col items-start gap-3">
      <h1 className="text-2xl font-bold">{strings.materials.notFound.title}</h1>
      <p className="text-slate-600">{strings.materials.notFound.body}</p>
      <Link className="text-sm text-slate-900 underline" to="/subjects">
        {strings.materials.back}
      </Link>
    </section>
  )
}

/** One page per subject: the key drops the state of the previous subject when the route changes. */
export default function TeacherActivityPage() {
  const { subjectId = '' } = useParams()
  return <ActivityContent key={subjectId} subjectId={subjectId} />
}

function ActivityContent({ subjectId }: { subjectId: string }) {
  const { user } = useSession()
  const query = useActivity(user?.id ?? '', subjectId)
  const error = query.error instanceof ApiError ? query.error : null

  if (error?.status === 403) return <ForbiddenPage />
  if (error?.status === 404 || error?.status === 422) return <NotAvailable />
  if (query.isPending || error?.status === 401) return <LoadingState label={text.loading} />
  if (query.data === undefined) {
    return (
      <ErrorState
        message={error ? messageFor(error) : strings.errors.unknown}
        onRetry={() => void query.refetch()}
      />
    )
  }
  return <ActivityView subjectId={subjectId} data={query.data} />
}

/** The loaded page: its heading takes the focus once, so a keyboard user lands on the new screen. */
function ActivityView({ subjectId, data }: { subjectId: string; data: ActivityResponse }) {
  const heading = useFocusOnMount<HTMLHeadingElement>()
  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm text-slate-900 underline" to={`/subjects/${subjectId}`}>
        {text.back}
      </Link>
      <h1 ref={heading} tabIndex={-1} className="text-2xl font-bold">
        {text.title}
      </h1>
      <ActivityDashboard data={data} />
    </div>
  )
}
