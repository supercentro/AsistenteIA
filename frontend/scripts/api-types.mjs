// Generates src/types/api.generated.ts from docs/api-spec.yml, or checks that the committed file is current.
//   node scripts/api-types.mjs          write the file
//   node scripts/api-types.mjs --check  exit 1 when the committed file differs from a fresh generation
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import openapiTS, { astToString } from 'openapi-typescript'

const SPEC = new URL('../../docs/api-spec.yml', import.meta.url)
const TARGET = new URL('../src/types/api.generated.ts', import.meta.url)
const BANNER =
  '// GENERATED from docs/api-spec.yml by scripts/api-types.mjs. Do not edit by hand.\n' +
  '// Regenerate with `npm run generate:api`.\n\n'

const normalise = (text) => text.replace(/\r\n/g, '\n')

const generated = BANNER + normalise(astToString(await openapiTS(SPEC)))

if (process.argv.includes('--check')) {
  const current = existsSync(TARGET) ? normalise(readFileSync(TARGET, 'utf8')) : null
  if (current !== generated) {
    console.error(
      'src/types/api.generated.ts is missing or out of date with docs/api-spec.yml. Run `npm run generate:api` and commit the result.',
    )
    process.exit(1)
  }
  console.log('API types are up to date.')
} else {
  writeFileSync(TARGET, generated)
  console.log('Wrote src/types/api.generated.ts')
}
