/** `2026-03-02` as `02/03/2026`; the API dates are calendar days in UTC and are not converted. */
export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split('-')
  return `${day}/${month}/${year}`
}

/** A share between 0 and 1 as `20,0 %`. */
export function formatShare(share: number): string {
  return `${(share * 100).toFixed(1).replace('.', ',')} %`
}

/** The width of a bar in whole percent, between 0 and 100. */
export function barWidth(value: number, maximum: number): string {
  if (maximum <= 0) return '0%'
  return `${Math.min(100, Math.max(0, Math.round((value / maximum) * 100)))}%`
}
