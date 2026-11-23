import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  children: ReactNode
}

/** A label and its value as a term and its definition, so the pair is read together. */
export function MetricCard({ label, children }: MetricCardProps) {
  return (
    <div className="rounded-md border border-slate-300 bg-white p-4">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-bold text-slate-900">{children}</dd>
    </div>
  )
}
