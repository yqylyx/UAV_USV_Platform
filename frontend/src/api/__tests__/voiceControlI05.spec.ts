import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { VoicePlanGuardRequest } from '@/types/voiceControl'

beforeEach(() => { vi.resetModules(); vi.stubEnv('VITE_VOICE_P0_MOCK', 'true') })
afterEach(() => { vi.unstubAllEnvs() })

it.each([
  ['confirm', 2, 400, 'INVALID_REQUEST'],
  ['confirm', 1, 409, 'PLAN_MISMATCH'],
  ['cancel', 2, 400, 'INVALID_REQUEST'],
  ['cancel', 1, 409, 'PLAN_MISMATCH'],
] as const)('I05 mock %s version %s returns %s without changing proposal', async (operation, version, status, code) => {
  const api = await import('@/api/voiceControl')
  const context = (await api.fetchVoiceContexts())[0]!
  const proposal = await api.createVoiceProposal({ runtimeRef: context.runtimeRef, runtimeGeneration: context.runtimeGeneration, expectedContextVersion: context.contextVersion, intent: 'MISSION_PAUSE' }, crypto.randomUUID())
  const request = { expectedPlanVersion: version, expectedPlanHash: '0'.repeat(64) } as unknown as VoicePlanGuardRequest
  const call = operation === 'confirm' ? api.confirmVoiceProposal : api.cancelVoiceProposal
  await expect(call(proposal.proposalId, request, crypto.randomUUID())).rejects.toMatchObject({ status, code })
  expect(await api.fetchVoiceProposal(proposal.proposalId)).toEqual(proposal)
  expect(proposal.executionId).toBeNull()
})
