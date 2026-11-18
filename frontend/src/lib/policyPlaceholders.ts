const MARKER = '[A COMPLETAR'

/** Every string of the tree that still holds an owner input marked `[A COMPLETAR ...]`. */
export function findOwnerPlaceholders(value: unknown): string[] {
  if (typeof value === 'string') {
    return value.includes(MARKER) ? [value] : []
  }
  if (Array.isArray(value)) {
    return value.flatMap(findOwnerPlaceholders)
  }
  if (typeof value === 'object' && value !== null) {
    return Object.values(value).flatMap(findOwnerPlaceholders)
  }
  return []
}
