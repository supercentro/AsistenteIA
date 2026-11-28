import { useEffect, useRef, useState, type FormEvent } from 'react'
import { formatDay } from '../lib/activityFormat'
import { strings } from '../lib/strings.es'
import {
  MAX_TOPICS,
  nextMonday,
  pagesChanged,
  readRows,
  type TopicInput,
  type TopicRow,
} from '../lib/topicDefinition'
import { Alert } from './Alert'
import { Button } from './Button'
import { FormField } from './FormField'

const text = strings.topics.editor

interface TopicEditorProps {
  saved: TopicInput[]
  lastPage: number
  /** The topics of this document were saved before, also if later cleared. */
  savedBefore: boolean
  saving: boolean
  /** Text of a refused save, shown with the typed rows kept. */
  failure: string | null
  onSave: (topics: TopicInput[]) => void
}

function toRows(topics: TopicInput[]): TopicRow[] {
  return topics.map((topic, index) => ({
    key: index,
    title: topic.title,
    from: String(topic.start_page),
    to: String(topic.end_page),
  }))
}

/** The whole set as rows; it is saved at once, with a warning when figures would restart. */
export function TopicEditor({
  saved,
  lastPage,
  savedBefore,
  saving,
  failure,
  onSave,
}: TopicEditorProps) {
  const [rows, setRows] = useState<TopicRow[]>(() => toRows(saved))
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<TopicInput[] | null>(null)
  const [added, setAdded] = useState<number | null>(null)
  const nextKey = useRef(saved.length)
  const addRef = useRef<HTMLButtonElement>(null)
  const warningRef = useRef<HTMLDivElement>(null)
  const addedRef = useRef<HTMLInputElement>(null)
  const saveRef = useRef<HTMLButtonElement>(null)
  const cancelled = useRef(false)

  // The warning takes the focus; cancelling it gives the focus back to the save button.
  useEffect(() => {
    if (pending) warningRef.current?.focus()
    else if (cancelled.current) {
      cancelled.current = false
      saveRef.current?.focus()
    }
  }, [pending])

  // A new row takes the focus, so that typing can go on with the keyboard.
  useEffect(() => {
    if (added !== null) addedRef.current?.focus()
  }, [added])

  function edit(key: number, field: 'title' | 'from' | 'to', value: string) {
    setPending(null)
    setRows((current) => current.map((row) => (row.key === key ? { ...row, [field]: value } : row)))
  }

  function add() {
    const key = nextKey.current
    nextKey.current += 1
    setPending(null)
    setAdded(key)
    setRows((current) => [...current, { key, title: '', from: '', to: '' }])
  }

  function remove(key: number) {
    setPending(null)
    setRows((current) => current.filter((row) => row.key !== key))
    addRef.current?.focus()
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (saving) return
    const result = readRows(rows, lastPage, saved)
    if ('error' in result) {
      setPending(null)
      setError(result.error === 'pages' ? text.errors.pages(lastPage) : text.errors[result.error])
      return
    }
    setError(null)
    if (savedBefore && pagesChanged(result.topics, saved)) {
      setPending(result.topics)
      return
    }
    onSave(result.topics)
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">{text.pagesHelp(lastPage)}</p>
      {rows.length === 0 ? <p className="text-slate-600">{text.empty}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row, index) => (
          <li
            key={row.key}
            className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 sm:flex-row sm:items-end"
          >
            <div className="min-w-0 flex-1">
              <FormField
                name={`title-${row.key}`}
                label={`${text.fieldTitle} ${index + 1}`}
                value={row.title}
                readOnly={saving}
                ref={row.key === added ? addedRef : undefined}
                onChange={(event) => edit(row.key, 'title', event.target.value)}
              />
            </div>
            <div className="sm:w-36">
              <FormField
                name={`from-${row.key}`}
                label={`${text.from} ${index + 1}`}
                value={row.from}
                readOnly={saving}
                inputMode="numeric"
                onChange={(event) => edit(row.key, 'from', event.target.value)}
              />
            </div>
            <div className="sm:w-36">
              <FormField
                name={`to-${row.key}`}
                label={`${text.to} ${index + 1}`}
                value={row.to}
                readOnly={saving}
                inputMode="numeric"
                onChange={(event) => edit(row.key, 'to', event.target.value)}
              />
            </div>
            <Button variant="secondary" disabled={saving} onClick={() => remove(row.key)}>
              {text.remove(index + 1)}
            </Button>
          </li>
        ))}
      </ul>
      <div>
        <Button
          ref={addRef}
          variant="secondary"
          disabled={saving || rows.length >= MAX_TOPICS}
          onClick={add}
        >
          {text.add}
        </Button>
      </div>
      {error || failure ? <Alert variant="error">{error ?? failure}</Alert> : null}
      {pending ? (
        <div
          ref={warningRef}
          role="group"
          aria-labelledby="topics-warning"
          tabIndex={-1}
          className="flex flex-col gap-2 rounded-md border border-amber-400 bg-amber-50 p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
        >
          <p id="topics-warning" className="font-medium text-amber-900">
            {text.warning.question}
          </p>
          <p className="text-sm text-amber-900">{text.warning.body(formatDay(nextMonday()))}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              pending={saving}
              onClick={() => {
                onSave(pending)
                setPending(null)
              }}
            >
              {text.warning.confirm}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                cancelled.current = true
                setPending(null)
              }}
            >
              {text.warning.cancel}
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button ref={saveRef} type="submit" pending={saving}>
            {saving ? text.saving : text.save}
          </Button>
        </div>
      )}
    </form>
  )
}
