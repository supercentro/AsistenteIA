interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 p-6 text-center text-slate-600">
      <p>{message}</p>
    </div>
  )
}
