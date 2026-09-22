import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import { useVoiceControlStore } from '@/stores/voiceControl'
import type {
  VoiceExecution,
  VoiceProposal,
  VoiceRuntimeContext,
} from '@/types/voiceControl'

const voiceApi = vi.hoisted(() => ({
  cancelVoiceProposal: vi.fn(),
  confirmVoiceProposal: vi.fn(),
  createVoiceProposal: vi.fn(),
  createVoicePresentationChallenge: vi.fn(),
  fetchVoiceContexts: vi.fn(),
  fetchVoiceExecution: vi.fn(),
  fetchVoicePresentationBinding: vi.fn(),
  fetchVoiceProposal: vi.fn(),
  replaceVoicePresentationBinding: vi.fn(),
  reportVoicePresentation: vi.fn(),
}))

vi.mock('@/api/voiceControl', () => voiceApi)

const context: VoiceRuntimeContext = {
  runtimeRef: '11111111-1111-4111-8111-111111111111',
  runtimeGeneration: '22222222-2222-4222-8222-222222222222',
  contextVersion: 3,
  stateVersion: 2,
  runtimeScope: 'MISSION_CENTER',
  runtimeKind: 'STANDALONE_ALGORITHM',
  executionBackend: 'PYTHON_SIMULATION',
  algorithmRunId: '178980000001',
  missionId: null,
  missionRunId: null,
  state: 'RUNNING',
  protocolVersion: 'algorithm.command.v1',
  capabilities: ['START', 'PAUSE', 'RESUME', 'STOP'],
  lastHeartbeatReceivedAt: '2026-09-21T00:00:00.000Z',
  latestFrameSequence: 12,
  sceneReady: true,
}

function execution(overrides: Partial<VoiceExecution> = {}): VoiceExecution {
  return {
    executionId: '33333333-3333-4333-8333-333333333333',
    proposalId: '44444444-4444-4444-8444-444444444444',
    commandId: '55555555-5555-4555-8555-555555555555',
    runtimeRef: context.runtimeRef,
    runtimeGeneration: context.runtimeGeneration,
    action: 'START',
    state: 'SUCCEEDED',
    outcome: 'SUCCESS',
    errorCode: null,
    timedOutAt: null,
    presentationStatus: 'PENDING',
    createdAt: '2026-09-21T00:00:00.000Z',
    updatedAt: '2026-09-21T00:00:01.000Z',
    ...overrides,
  }
}

const proposal: VoiceProposal = {
  proposalId: '44444444-4444-4444-8444-444444444444',
  status: 'AWAITING_CONFIRMATION',
  planVersion: 1,
  planHash: 'abc123',
  plan: {
    runtimeRef: context.runtimeRef,
    runtimeGeneration: context.runtimeGeneration,
    contextVersion: context.contextVersion,
    stateVersion: context.stateVersion,
    action: 'START',
    explicitDeviceCodes: ['UAV-001', 'USV-001'],
    policyVersion: 'voice-p0.v1',
  },
  requiresConfirmation: true,
  createdAt: '2026-09-21T00:00:00.000Z',
  expiresAt: '2026-09-21T00:00:30.000Z',
  executionId: null,
}

function setupStore() {
  setActivePinia(createPinia())
  useAuthStore().user = { username: 'admin', role: 'ADMIN' }
  const store = useVoiceControlStore()
  store.contexts = [context]
  store.selectedRuntimeRef = context.runtimeRef
  store.expectedAlgorithmRunId = context.algorithmRunId
  return store
}

describe('voiceControl store polling and recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    voiceApi.fetchVoiceContexts.mockResolvedValue([context])
  })

  it('continues querying after algorithm success while presentation is PENDING', async () => {
    const store = setupStore()
    store.execution = execution()
    voiceApi.fetchVoiceExecution.mockResolvedValue(execution({ presentationStatus: 'STALE' }))

    await store.poll()

    expect(voiceApi.fetchVoiceExecution).toHaveBeenCalledWith(store.execution.executionId)
    expect(store.execution.presentationStatus).toBe('STALE')
  })

  it('stops querying after presentation becomes REPORTED_APPLIED', async () => {
    const store = setupStore()
    store.execution = execution({ presentationStatus: 'REPORTED_APPLIED' })

    await store.poll()

    expect(voiceApi.fetchVoiceExecution).not.toHaveBeenCalled()
  })

  it('stops querying an algorithm failure terminal state', async () => {
    const store = setupStore()
    store.execution = execution({ state: 'FAILED', outcome: 'FAILED', presentationStatus: 'NOT_REQUIRED' })

    await store.poll()

    expect(voiceApi.fetchVoiceExecution).not.toHaveBeenCalled()
  })

  it('keeps reconciling a TIMED_OUT execution because its result is still unknown', async () => {
    const store = setupStore()
    store.execution = execution({ state: 'TIMED_OUT', outcome: 'UNKNOWN', timedOutAt: '2026-09-21T00:00:02.000Z' })
    voiceApi.fetchVoiceExecution.mockResolvedValue(execution())

    await store.poll()

    expect(voiceApi.fetchVoiceExecution).toHaveBeenCalledOnce()
    expect(store.execution.state).toBe('SUCCEEDED')
  })

  it('restores the same execution from the user-scoped local recovery record', async () => {
    const store = setupStore()
    const savedExecution = execution({ presentationStatus: 'STALE' })
    localStorage.setItem('voice-p0.active-command.v2:admin', JSON.stringify({ executionId: savedExecution.executionId }))
    voiceApi.fetchVoiceExecution.mockResolvedValue(savedExecution)

    await store.recover()

    expect(voiceApi.fetchVoiceExecution).toHaveBeenCalledWith(savedExecution.executionId)
    expect(store.execution).toEqual(savedExecution)
  })

  it('replays an unknown confirmation with the original body and idempotency key', async () => {
    const store = setupStore()
    const idempotencyKey = '66666666-6666-4666-8666-666666666666'
    const body = { expectedPlanVersion: 1 as const, expectedPlanHash: proposal.planHash }
    localStorage.setItem('voice-p0.operation-journal.v1:admin', JSON.stringify({
      userScope: 'admin',
      runtimeRef: context.runtimeRef,
      runtimeGeneration: context.runtimeGeneration,
      kind: 'CONFIRM',
      method: 'POST',
      path: `/api/voice/commands/${proposal.proposalId}/confirm`,
      idempotencyKey,
      body,
      resourceId: proposal.proposalId,
      phase: 'RESPONSE_UNKNOWN',
      updatedAt: '2026-09-21T00:00:02.000Z',
    }))
    voiceApi.fetchVoiceProposal.mockResolvedValue(proposal)
    voiceApi.confirmVoiceProposal.mockResolvedValue({ proposal: { ...proposal, status: 'CONFIRMED' }, execution: execution() })
    voiceApi.fetchVoiceExecution.mockResolvedValue(execution())

    await store.recover()

    expect(voiceApi.confirmVoiceProposal).toHaveBeenCalledWith(proposal.proposalId, body, idempotencyKey)
    expect(store.execution?.executionId).toBe(execution().executionId)
  })

  it('does not clear an unknown control response when presentation binding succeeds', async () => {
    const store = setupStore()
    store.responseUnknown = true
    store.error = '请求结果未知，请重新查询'
    store.errorCode = 'NETWORK_ERROR'
    voiceApi.fetchVoicePresentationBinding.mockResolvedValue({
      bindingId: '77777777-7777-4777-8777-777777777777',
      runtimeGeneration: context.runtimeGeneration,
    })
    voiceApi.replaceVoicePresentationBinding.mockResolvedValue({
      bindingId: '88888888-8888-4888-8888-888888888888',
      runtimeGeneration: context.runtimeGeneration,
    })

    await store.takePresentationBinding()

    expect(store.responseUnknown).toBe(true)
  })

  it('allows an operator command while a presentation request has its own recovery journal', async () => {
    const store = setupStore()
    store.beginJournal('PRESENTATION_CHALLENGE', '/presentation/challenges', {
      runtimeGeneration: context.runtimeGeneration,
      bindingId: '77777777-7777-4777-8777-777777777777',
      kind: 'SCENE_READY',
      executionId: null,
    })
    voiceApi.createVoiceProposal.mockResolvedValue(proposal)

    await store.propose('MISSION_PAUSE')

    expect(voiceApi.createVoiceProposal).toHaveBeenCalledOnce()
    expect(store.responseUnknown).toBe(false)
  })
})
