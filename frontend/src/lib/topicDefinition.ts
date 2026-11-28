/** Rules of the topic editor. The API decides; these only avoid sending what it would refuse. */

export const MAX_TOPICS = 100
export const MAX_TITLE_LENGTH = 200

export interface TopicRow {
  /** Local identity of the row, never sent. */
  key: number
  title: string
  from: string
  to: string
}

export interface TopicInput {
  title: string
  start_page: number
  end_page: number
}

export type DefinitionError = 'title' | 'pages' | 'overlap'

function page(value: string): number {
  return /^\s*\d+\s*$/.test(value) ? Number(value) : Number.NaN
}

function ranges(topics: TopicInput[]): string {
  return topics
    .map((topic) => `${topic.start_page}-${topic.end_page}`)
    .sort()
    .join(',')
}

/** True when the pages differ from the saved ones (a change of titles alone is not one). */
export function pagesChanged(topics: TopicInput[], saved: TopicInput[]): boolean {
  return ranges(topics) !== ranges(saved)
}

export function readRows(
  rows: TopicRow[],
  lastPage: number,
  saved: TopicInput[],
): { topics: TopicInput[] } | { error: DefinitionError } {
  const topics: TopicInput[] = []
  for (const row of rows) {
    const title = row.title.trim().replace(/\s+/g, ' ')
    // Counted in code points, as the API counts them, not in UTF-16 units.
    const length = [...title].length
    if (length === 0 || length > MAX_TITLE_LENGTH) return { error: 'title' }
    const start = page(row.from)
    const end = page(row.to)
    if (!(start >= 1 && start <= end && end <= lastPage)) return { error: 'pages' }
    topics.push({ title, start_page: start, end_page: end })
  }
  if (pagesChanged(topics, saved)) {
    const ordered = [...topics].sort((a, b) => a.start_page - b.start_page)
    const overlaps = ordered.some(
      (topic, index) => index > 0 && topic.start_page <= ordered[index - 1]!.end_page,
    )
    if (overlaps) return { error: 'overlap' }
  }
  return { topics }
}

/** The Monday (UTC) after the current week, as `YYYY-MM-DD`: from there a change counts. */
export function nextMonday(now: Date = new Date()): string {
  const sinceMonday = (now.getUTCDay() + 6) % 7
  const monday = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() - sinceMonday + 7,
  )
  return new Date(monday).toISOString().slice(0, 10)
}
