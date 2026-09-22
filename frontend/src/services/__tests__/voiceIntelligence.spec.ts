import { describe, expect, it } from 'vitest'

import { parseMockVoiceIntent } from '@/services/voiceIntelligence'
import type { VoiceParseRequest } from '@/types/voiceIntelligence'

function request(text: string, allowedActions: VoiceParseRequest['allowedActions'] = ['START', 'PAUSE', 'RESUME', 'STOP']): VoiceParseRequest {
  return {
    requestId: '11111111-1111-4111-8111-111111111111', text, locale: 'zh-CN',
    allowedActions, availableDeviceCodes: ['UAV-001', 'USV-001'],
  }
}

describe('provider-neutral voice intent mock', () => {
  it.each([
    ['开始任务', 'START', 'MISSION_START'],
    ['暂停当前任务', 'PAUSE', 'MISSION_PAUSE'],
    ['继续执行', 'RESUME', 'MISSION_RESUME'],
    ['停止任务', 'STOP', 'MISSION_STOP'],
  ])('maps %s to a candidate without executing it', (text, action, intent) => {
    const result = parseMockVoiceIntent(request(text))
    expect(result).toMatchObject({ status: 'CANDIDATE', action, intent })
  })

  it('does not turn a negated sentence into an action', () => {
    expect(parseMockVoiceIntent(request('不要停止任务'))).toMatchObject({
      status: 'NOT_ACTIONABLE', reason: 'NEGATED_ACTION',
    })
  })

  it('requires clarification when more than one action appears', () => {
    expect(parseMockVoiceIntent(request('先暂停然后继续'))).toMatchObject({
      status: 'NEEDS_CLARIFICATION', reason: 'AMBIGUOUS_ACTION',
    })
  })

  it('rejects algorithm capabilities that are not part of P0', () => {
    expect(parseMockVoiceIntent(request('开始围捕目标'))).toMatchObject({
      status: 'UNSUPPORTED', reason: 'UNSUPPORTED_CAPABILITY',
    })
  })

  it('does not degrade a device command into whole-team control', () => {
    expect(parseMockVoiceIntent(request('暂停一号无人艇'))).toMatchObject({
      status: 'UNSUPPORTED', reason: 'UNSUPPORTED_TARGETING',
    })
  })

  it('checks the capabilities declared by the active runtime', () => {
    expect(parseMockVoiceIntent(request('暂停任务', ['START']))).toMatchObject({
      status: 'UNSUPPORTED', reason: 'UNSUPPORTED_CAPABILITY',
    })
  })
})
