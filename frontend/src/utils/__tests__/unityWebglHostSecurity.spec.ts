import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

type MessageSourceGuard = (
  event: { origin: string; source: object },
  expectedOrigin: string,
  expectedParent: object,
) => boolean

function loadHostGuard() {
  const hostPath = resolve(process.cwd(), 'public/unity-virtual-fleet/index.html')
  const html = readFileSync(hostPath, 'utf8')
  const source = html.match(
    /function isTrustedParentMessageEvent\(event, expectedOrigin, expectedParent\) \{[\s\S]*?\n      \}/,
  )?.[0]

  expect(source).toBeTruthy()
  expect(html).toContain(
    'isTrustedParentMessageEvent(event, window.location.origin, window.parent)',
  )

  return new Function(
    `${source}; return isTrustedParentMessageEvent;`,
  )() as MessageSourceGuard
}

describe('Unity WebGL host message source guard', () => {
  it('X06 rejects the same origin when the sender is not window.parent', () => {
    const guard = loadHostGuard()
    const parentWindow = {}

    expect(guard(
      { origin: 'http://127.0.0.1:15174', source: {} },
      'http://127.0.0.1:15174',
      parentWindow,
    )).toBe(false)
  })

  it('accepts only the expected origin and parent together', () => {
    const guard = loadHostGuard()
    const parentWindow = {}

    expect(guard(
      { origin: 'http://127.0.0.1:15174', source: parentWindow },
      'http://127.0.0.1:15174',
      parentWindow,
    )).toBe(true)
    expect(guard(
      { origin: 'http://attacker.invalid', source: parentWindow },
      'http://127.0.0.1:15174',
      parentWindow,
    )).toBe(false)
  })
})
