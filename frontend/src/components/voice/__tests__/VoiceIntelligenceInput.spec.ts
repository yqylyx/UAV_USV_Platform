import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '@/api/http'
import type { VoiceIntelligenceAdapter } from '@/types/voiceIntelligence'

import VoiceIntelligenceInput from '@/components/voice/VoiceIntelligenceInput.vue'
import { createMockVoiceIntelligenceAdapter } from '@/services/voiceIntelligence'

function mountInput() {
  return mount(VoiceIntelligenceInput, {
    props: {
      adapter: createMockVoiceIntelligenceAdapter(),
      allowedActions: ['START', 'PAUSE', 'RESUME', 'STOP'],
      deviceCodes: ['UAV-001', 'USV-001'],
      runtimeContext: null,
      operatorScope: 'admin',
      allowMockSubmission: true,
      actionDisabledReason: () => '',
    },
  })
}

describe('VoiceIntelligenceInput', () => {
  function backendInput(parse: VoiceIntelligenceAdapter['parse']) {
    return mount(VoiceIntelligenceInput, { props: {
      adapter: { name: 'platform-backend', mode: 'BACKEND', transcribe: vi.fn(), parse },
      allowedActions: ['PAUSE'], deviceCodes: [], operatorScope: 'admin',
    } })
  }
  const successfulParse: VoiceIntelligenceAdapter['parse'] = async input => ({
    status: 'CANDIDATE', requestId: input.requestId, action: 'PAUSE', intent: 'MISSION_PAUSE',
    normalizedText: input.text, confidence: null, provider: 'test-fixture', model: 'fixed-v1',
  })
  it('recovers with the same body and ID and emits the backend interpretation ID', async () => {
    const parse = vi.fn().mockRejectedValueOnce(new Error('network lost')).mockImplementation(successfulParse)
    const wrapper = backendInput(parse)
    await wrapper.get('textarea').setValue(' 暂停任务 ')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    await wrapper.findAll('button').find(b => b.text() === '使用原请求恢复查询')!.trigger('click')
    await flushPromises()
    const [first, second] = parse.mock.calls.map(call => call[0])
    expect(first.requestId).toBe(second.requestId)
    expect(first.text).toBe(second.text)
    expect(first.runtimeContext).toEqual(second.runtimeContext)
    expect(wrapper.text()).toContain('后端测试适配器')
    await wrapper.get('.candidate button').trigger('click')
    expect(wrapper.emitted('candidate')).toEqual([['MISSION_PAUSE', first.requestId]])
    wrapper.unmount()
  })
  it('ignores a late result from the previous operator', async () => {
    let resolve!: () => void
    const parse = vi.fn(input => new Promise<any>(done => { resolve = async () => done(await successfulParse(input)) }))
    const wrapper = backendInput(parse)
    await wrapper.get('textarea').setValue('暂停')
    await wrapper.findAll('button')[1]!.trigger('click')
    await wrapper.setProps({ operatorScope: 'operator-b' })
    resolve()
    await flushPromises()
    expect(wrapper.find('.candidate').exists()).toBe(false)
    expect(parse.mock.calls[0]![0].signal.aborted).toBe(true)
    wrapper.unmount()
  })
  it('clears candidates when the runtime generation changes', async () => {
    const wrapper = backendInput(successfulParse)
    await wrapper.get('textarea').setValue('暂停')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()
    await wrapper.setProps({ runtimeContext: { runtimeRef: 'new-ref', runtimeGeneration: 'new-generation', contextVersion: 0 } })
    expect(wrapper.find('.candidate').exists()).toBe(false)
    wrapper.unmount()
  })
  it('keeps input during same-generation context version refreshes', async () => {
    const wrapper = backendInput(successfulParse)
    await wrapper.setProps({ runtimeContext: {
      runtimeRef: 'runtime-ref', runtimeGeneration: 'runtime-generation', contextVersion: 1,
    } })
    await wrapper.get('textarea').setValue('开始任务')
    await wrapper.setProps({ runtimeContext: {
      runtimeRef: 'runtime-ref', runtimeGeneration: 'runtime-generation', contextVersion: 2,
    } })
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('开始任务')
    wrapper.unmount()
  })
  it('blocks new input after server revocation', async () => {
    const wrapper = backendInput(vi.fn().mockRejectedValue(new ApiClientError('撤权', 403, 'FORBIDDEN')))
    await wrapper.get('textarea').setValue('暂停')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect(wrapper.find('.candidate').exists()).toBe(false)
    wrapper.unmount()
  })
  it('blocks local parsing mock from submitting to real P0', async () => {
    const wrapper = mountInput()
    await wrapper.setProps({ allowMockSubmission: false })
    await wrapper.get('textarea').setValue('暂停')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect((wrapper.get('.candidate button').element as HTMLButtonElement).disabled).toBe(true)
    wrapper.unmount()
  })
  it('preserves overlong text and requires editing', async () => {
    const parse = vi.fn(successfulParse)
    const wrapper = backendInput(parse)
    await wrapper.get('textarea').setValue('字'.repeat(201))
    expect(wrapper.text()).toContain('201 字')
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(parse).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('keeps the transcript editable and emits only after candidate review', async () => {
    const wrapper = mountInput()
    await wrapper.get('textarea').setValue('暂停当前任务')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('候选指令')
    expect(wrapper.text()).toContain('PAUSE')
    expect(wrapper.emitted('candidate')).toBeUndefined()

    await wrapper.get('.candidate button').trigger('click')
    expect(wrapper.emitted('candidate')).toEqual([['MISSION_PAUSE']])
  })

  it('blocks negated commands before proposal creation', async () => {
    const wrapper = mountInput()
    await wrapper.get('textarea').setValue('不要停止任务')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('检测到否定表达')
    expect(wrapper.find('.candidate').exists()).toBe(false)
    expect(wrapper.emitted('candidate')).toBeUndefined()
  })

  it('does not downgrade a single-device command to a fleet action', async () => {
    const wrapper = mountInput()
    await wrapper.get('textarea').setValue('暂停一号无人艇')
    await wrapper.findAll('button')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('暂不支持指定单台设备')
    expect(wrapper.find('.candidate').exists()).toBe(false)
  })

  it('clears unsubmitted text when the operator changes', async () => {
    const wrapper = mountInput()
    await wrapper.get('textarea').setValue('暂停当前任务')
    await wrapper.setProps({ operatorScope: 'operator-b' })

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.text()).toContain('操作员已切换')
  })
})
