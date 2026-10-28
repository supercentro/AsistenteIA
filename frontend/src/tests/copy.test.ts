import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const SRC = join(process.cwd(), 'src')
const COPY_ATTRIBUTES = new Set(['aria-label', 'aria-description', 'placeholder', 'title', 'alt'])
const HAS_LETTERS = /\p{L}/u

function sourceFiles(directory: string): string[] {
  return readdirSync(join(SRC, directory), { withFileTypes: true })
    .filter(
      (entry) => entry.isFile() && /\.tsx$/.test(entry.name) && !/\.test\.tsx$/.test(entry.name),
    )
    .map((entry) => join(SRC, directory, entry.name))
}

/** User-visible literals in JSX: text between tags and the value of accessible-name attributes. */
export function findInlineCopy(source: string, fileName = 'file.tsx'): string[] {
  const file = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  )
  const found: string[] = []
  const visit = (node: ts.Node): void => {
    if (ts.isJsxText(node) && HAS_LETTERS.test(node.text)) {
      found.push(node.text.trim())
    }
    if (
      ts.isJsxAttribute(node) &&
      COPY_ATTRIBUTES.has(node.name.getText(file)) &&
      node.initializer &&
      ts.isStringLiteral(node.initializer) &&
      HAS_LETTERS.test(node.initializer.text)
    ) {
      found.push(node.initializer.text)
    }
    if (
      ts.isJsxExpression(node) &&
      node.expression &&
      ts.isStringLiteralLike(node.expression) &&
      HAS_LETTERS.test(node.expression.text) &&
      !(node.parent && ts.isJsxAttribute(node.parent))
    ) {
      found.push(node.expression.text)
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return found
}

describe('findInlineCopy (the detector itself)', () => {
  it('finds text nodes, copy attributes and string expressions', () => {
    expect(findInlineCopy('const a = <p>Hola mundo</p>')).toEqual(['Hola mundo'])
    expect(findInlineCopy('const a = <input aria-label="Correo" />')).toEqual(['Correo'])
    expect(findInlineCopy("const a = <p>{'Texto'}</p>")).toEqual(['Texto'])
  })

  it('ignores copy that comes from the strings module and non-copy literals', () => {
    expect(findInlineCopy('const a = <p aria-label={strings.x}>{strings.y}</p>')).toEqual([])
    expect(findInlineCopy('const a = <input type="email" className="p-4" name="email" />')).toEqual(
      [],
    )
    expect(findInlineCopy('const a = <p>{value} · {other}</p>')).toEqual([])
  })
})

describe('UI copy lives in the strings module', () => {
  it.each(['pages', 'components'])('has no inline Spanish copy in src/%s', (directory) => {
    const offenders = sourceFiles(directory).flatMap((file) =>
      findInlineCopy(readFileSync(file, 'utf8'), file).map((text) => `${file}: "${text}"`),
    )

    expect(offenders).toEqual([])
  })
})
