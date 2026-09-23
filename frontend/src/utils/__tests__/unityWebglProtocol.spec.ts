import { describe, expect, it } from 'vitest'

import { createVueConsoleEnvelope, unwrapUnityPresentationMessage } from '@/utils/unityWebglProtocol'

describe('createVueConsoleEnvelope', () => {
  it('wraps presentation messages for the Unity WebGL listener', () => {
    const message = {
      type: 'PRESENTATION_PROBE',
      protocolVersion: 'unity.presentation.v1',
      requestId: 'challenge-1',
    }

    expect(createVueConsoleEnvelope('VIRTUAL_FLEET', 'virtual-fleet-unity-01', message)).toEqual({
      source: 'vue-console',
      runtimeScope: 'VIRTUAL_FLEET',
      runtimeInstanceId: 'virtual-fleet-unity-01',
      message,
    })
  })
})

describe('unwrapUnityPresentationMessage', () => {
  it('restores the presentation identity from the Unity WebGL payload', () => {
    expect(unwrapUnityPresentationMessage({
      type: 'PRESENTATION_REPORT',
      requestId: 'probe-1',
      payload: {
        protocolVersion: 'unity.presentation.v1',
        runtimeRef: 'runtime-1',
        runtimeGeneration: 'generation-1',
        bindingId: 'binding-1',
        unityInstanceId: 'unity-1',
        sceneRevision: 2,
        sequence: 7,
        kind: 'SCENE_READY',
        executionId: null,
        frameSequence: 11,
        applied: true,
      },
    })).toMatchObject({
      type: 'PRESENTATION_REPORT',
      requestId: 'probe-1',
      runtimeRef: 'runtime-1',
      bindingId: 'binding-1',
      executionId: null,
      applied: true,
    })
  })
})
