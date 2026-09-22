import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

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
      actionDisabledReason: () => '',
    },
  })
}

describe('VoiceIntelligenceInput', () => {
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
