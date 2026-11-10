import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

// A release is only published once the same checks as a pull request have passed.
const workflows = join(__dirname, '../../../.github/workflows')
const read = (name: string) => readFileSync(join(workflows, name), 'utf8')
const release = read('release.yml')

// The block of each top-level job: from `  name:` up to the next one.
const jobs = Object.fromEntries(
  [...release.split(/^jobs:\n/m)[1]!.matchAll(/^ {2}([\w-]+):\n((?: {4}.*\n|\n)*)/gm)].map((m) => [
    m[1]!,
    m[2]!,
  ]),
)

describe('release.yml', () => {
  it('ci.yml can be called from another workflow', () => {
    expect(read('ci.yml')).toMatch(/^ {2}workflow_call:/m)
  })

  it('the release runs ci.yml', () => {
    expect(
      Object.values(jobs).some((job) => job.includes('uses: ./.github/workflows/ci.yml')),
    ).toBe(true)
  })

  it('publishing waits for every check', () => {
    const callers = Object.entries(jobs)
      .filter(([, job]) => /uses: \.\/\.github\/workflows\//.test(job))
      .map(([name]) => name)
    const publish = Object.values(jobs).find((job) => job.includes('gh release'))!
    const needs = publish.match(/needs: \[([^\]]*)\]/)?.[1]?.split(/,\s*/) ?? []
    expect(callers.length).toBeGreaterThan(0)
    expect(needs.sort()).toEqual(callers.sort())
  })
})
