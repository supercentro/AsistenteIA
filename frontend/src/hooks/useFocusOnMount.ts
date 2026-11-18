import { useEffect, useRef } from 'react'

/** Moves focus to the element once, when the screen appears (the page heading). */
export function useFocusOnMount<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    ref.current?.focus()
  }, [])
  return ref
}
