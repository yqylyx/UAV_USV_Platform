import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/api/http', () => ({ http: { post: mocks.post }, ApiClientError: class extends Error {} }))
vi.mock('@/api/auth', () => ({ fetchCsrfToken: async () => ({ headerName: 'X-CSRF-TOKEN', token: 'test' }) }))
beforeEach(() => { vi.resetModules(); vi.stubEnv('VITE_VOICE_P0_MOCK', 'false'); mocks.post.mockResolvedValue({ data: { data: {} } }) })
afterEach(() => vi.unstubAllEnvs())
it.each([undefined, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'])('preserves optional source %s outside the unchanged P0 JSON body', async source => {
  const { createVoiceProposal } = await import('@/api/voiceControl')
  const body = { runtimeRef: 'ref', runtimeGeneration: 'generation', expectedContextVersion: 1, intent: 'MISSION_PAUSE' as const }
  await createVoiceProposal(body, 'key', source)
  const [, payload, options] = mocks.post.mock.calls.at(-1)!
  expect(payload).toEqual(body)
  expect(options.headers['X-Voice-Interpretation-ID']).toBe(source)
  expect(options.headers['Idempotency-Key']).toBe('key')
})
