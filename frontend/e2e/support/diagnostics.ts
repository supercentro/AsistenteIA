import type { ConsoleMessage, Frame, Page, TestInfo } from '@playwright/test'

/**
 * Diagnostic recorder for an intermittent failure (TD-068). It never changes what a test checks: it
 * only listens, and prints a timeline plus a last snapshot of the page when the test fails, so that
 * the CI log shows what happened when the confirmation group did not appear. Only the test that
 * asks for it is recorded. The data are the fictitious ones of the mocked suite.
 */

interface Entry {
  at: number
  kind: string
  detail: string
}

const MAX_ENTRIES = 400
const recorders = new Map<string, Entry[]>()

/** Start recording for this test. Call it before the first navigation. */
export async function recordDiagnostics(page: Page, testInfo: TestInfo): Promise<void> {
  const started = Date.now()
  const entries: Entry[] = []
  const add = (kind: string, detail: string) => {
    if (entries.length < MAX_ENTRIES) {
      entries.push({ at: Date.now() - started, kind, detail })
    }
  }
  recorders.set(testInfo.testId, entries)

  // The in-page events reach the recorder through a function that survives a page reload.
  await page.exposeFunction('__diagnose', (kind: string, detail: string) => add(kind, detail))
  await page.addInitScript(() => {
    const describe = (target: EventTarget | null): string => {
      if (!(target instanceof HTMLElement)) {
        return String(target)
      }
      const label = (target.getAttribute('aria-label') ?? target.innerText ?? '').slice(0, 40)
      const role = target.getAttribute('role')
      return `${target.tagName.toLowerCase()}${role ? `[role=${role}]` : ''} "${label.replace(/\s+/g, ' ')}"`
    }
    const send = (kind: string, detail: string) =>
      (window as unknown as { __diagnose: (k: string, d: string) => void }).__diagnose(kind, detail)
    send('page-start', location.href)
    document.addEventListener('focusin', (event) => send('focusin', describe(event.target)), true)
    document.addEventListener('focusout', (event) => send('focusout', describe(event.target)), true)
    document.addEventListener(
      'keydown',
      (event) => send('keydown', `${event.key} on ${describe(event.target)}`),
      true,
    )
    document.addEventListener('click', (event) => send('click', describe(event.target)), true)
    window.addEventListener('pagehide', () => send('pagehide', location.href))
    new MutationObserver((records) => {
      for (const record of records) {
        for (const node of [...Array.from(record.addedNodes), ...Array.from(record.removedNodes)]) {
          if (
            node instanceof HTMLElement &&
            (node.getAttribute('role') === 'group' || node.querySelector('[role=group]'))
          ) {
            send(
              record.addedNodes.length > 0 && Array.from(record.addedNodes).includes(node)
                ? 'group-added'
                : 'group-removed',
              describe(node),
            )
          }
        }
      }
    }).observe(document, { childList: true, subtree: true })
  })

  page.on('framenavigated', (frame: Frame) => {
    if (frame === page.mainFrame()) {
      add('navigated', frame.url())
    }
  })
  page.on('load', () => add('load', page.url()))
  page.on('console', (message: ConsoleMessage) => {
    if (['error', 'warning'].includes(message.type()) || message.text().includes('[vite]')) {
      add(`console.${message.type()}`, message.text().slice(0, 200))
    }
  })
  page.on('pageerror', (error) => add('pageerror', error.message.slice(0, 200)))
  page.on('requestfailed', (request) =>
    add('requestfailed', `${request.method()} ${request.url()}`),
  )
  page.on('response', (response) => {
    const url = response.url()
    if (url.includes('/api/v1/')) {
      add(
        'response',
        `${response.request().method()} ${url.split('/api/v1')[1]} ${response.status()}`,
      )
    }
  })
}

/** Print the timeline and a last snapshot when the test did not end as expected. */
export async function printDiagnosticsOnFailure(page: Page, testInfo: TestInfo): Promise<void> {
  const recorder = recorders.get(testInfo.testId)
  recorders.delete(testInfo.testId)
  if (!recorder || testInfo.status === testInfo.expectedStatus) {
    return
  }
  let snapshot: unknown = 'the page was not available'
  try {
    snapshot = await page.evaluate(() => {
      const active = document.activeElement
      return {
        url: location.href,
        hasFocus: document.hasFocus(),
        active: active
          ? `${active.tagName.toLowerCase()} "${(active as HTMLElement).innerText?.slice(0, 40) ?? ''}"`
          : null,
        groups: document.querySelectorAll('[role=group]').length,
        deleteButtons: Array.from(document.querySelectorAll('button'))
          .map((button) => button.innerText.slice(0, 50))
          .filter((label) => label.startsWith('Eliminar')),
        box:
          (document.querySelector('textarea') as HTMLTextAreaElement | null)?.value.length ?? null,
        text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 600),
      }
    })
  } catch (error) {
    snapshot = `snapshot failed: ${String(error).slice(0, 120)}`
  }
  const lines = recorder.map(
    (entry) => `${String(entry.at).padStart(6)} ms  ${entry.kind}  ${entry.detail}`,
  )
  const report = [
    `[TD-068 diagnostics] ${testInfo.title}`,
    `snapshot: ${JSON.stringify(snapshot)}`,
    'timeline:',
    ...lines,
    '[end of TD-068 diagnostics]',
  ]
  process.stdout.write(`\n${report.join('\n')}\n`)
}
