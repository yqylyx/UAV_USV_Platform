import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import VoiceP0ControlPanel from '@/components/voice/VoiceP0ControlPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { useVoiceControlStore } from '@/stores/voiceControl'
import type { VoiceExecution, VoiceRuntimeContext } from '@/types/voiceControl'

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
  lastHeartbeatReceivedAt: new Date().toISOString(),
  latestFrameSequence: 12,
  sceneReady: true,
}

function execution(presentationStatus: VoiceExecution['presentationStatus']): VoiceExecution {
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
    presentationStatus,
    createdAt: '2026-09-21T00:00:00.000Z',
    updatedAt: '2026-09-21T00:00:01.000Z',
  }
}

function mountPanel(presentationStatus: VoiceExecution['presentationStatus']) {
  const store = useVoiceControlStore()
  store.contexts = [context]
  store.selectedRuntimeRef = context.runtimeRef
  store.expectedAlgorithmRunId = context.algorithmRunId
  store.execution = execution(presentationStatus)
  store.selectAlgorithmRun = vi.fn().mockResolvedValue(true)
  store.recover = vi.fn().mockResolvedValue(undefined)
  store.refreshContexts = vi.fn().mockResolvedValue(true)
  store.poll = vi.fn().mockResolvedValue(undefined)

  return mount(VoiceP0ControlPanel, {
    props: {
      runtimeHint: {
        algorithmRunId: context.algorithmRunId,
        state: context.state,
        sceneReady: context.sceneReady,
        deviceCodes: ['UAV-001', 'USV-001'],
        latestFrameSequence: context.latestFrameSequence,
      },
      unitySession: { connected: false, unityInstanceId: 'unity-test', sceneRevision: 1 },
    },
  })
}

describe('VoiceP0ControlPanel presentation recovery UI', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    useAuthStore().user = { username: 'admin', role: 'ADMIN' }
  })

  it('shows a resync entry when a successful START presentation is STALE', () => {
    const wrapper = mountPanel('STALE')

    expect(wrapper.text()).toContain('Unity 展示已过期')
    expect(wrapper.get('button.presentation-resync').text()).toContain('重新同步画面')
    wrapper.unmount()
  })

  it('does not show the resync entry after Unity has reported the frame applied', () => {
    const wrapper = mountPanel('REPORTED_APPLIED')

    expect(wrapper.text()).toContain('Unity 已应用')
    expect(wrapper.find('button.presentation-resync').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not replace the presentation binding again when the same Unity session reconnects', async () => {
    const wrapper = mountPanel('REPORTED_APPLIED')
    const store = useVoiceControlStore()
    store.takePresentationBinding = vi.fn().mockImplementation(async () => {
      store.presentationBinding = {
        bindingId: '77777777-7777-4777-8777-777777777777',
        runtimeGeneration: context.runtimeGeneration,
      }
    })

    await wrapper.setProps({ unitySession: { connected: true, unityInstanceId: 'unity-test', sceneRevision: 1 } })
    await nextTick()
    await wrapper.setProps({ unitySession: { connected: false, unityInstanceId: 'unity-test', sceneRevision: 1 } })
    await wrapper.setProps({ unitySession: { connected: true, unityInstanceId: 'unity-test', sceneRevision: 1 } })
    await nextTick()

    expect(store.takePresentationBinding).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})
