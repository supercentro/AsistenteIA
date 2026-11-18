import { PRIVACY_POLICY_VERSION } from '../lib/privacyPolicy'
import { strings } from '../lib/strings.es'

interface PolicySection {
  heading: string
  paragraphs: readonly string[]
  items: readonly string[]
  notes?: readonly string[]
}

/** The text of the current privacy policy. One source for the public page and the consent screen. */
export function PolicyView() {
  const sections = Object.entries(strings.privacy.sections) as [string, PolicySection][]
  return (
    <article className="flex flex-col gap-6">
      <p className="text-sm text-slate-600">
        {strings.privacy.versionLabel(PRIVACY_POLICY_VERSION)}
      </p>
      <p>{strings.privacy.intro}</p>
      {sections.map(([id, section]) => (
        <section key={id} aria-labelledby={`policy-${id}`} className="flex flex-col gap-2">
          <h2 id={`policy-${id}`} className="text-lg font-semibold text-slate-900">
            {section.heading}
          </h2>
          {section.paragraphs.map((text) => (
            <p key={text} className="break-words">
              {text}
            </p>
          ))}
          {section.items.length > 0 ? (
            <ul className="list-disc space-y-1 pl-6">
              {section.items.map((text) => (
                <li key={text} className="break-words">
                  {text}
                </li>
              ))}
            </ul>
          ) : null}
          {(section.notes ?? []).map((text) => (
            <p key={text} className="break-words">
              {text}
            </p>
          ))}
        </section>
      ))}
    </article>
  )
}
