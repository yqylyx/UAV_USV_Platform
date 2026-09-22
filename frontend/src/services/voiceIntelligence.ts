import type { VoiceAction, VoiceIntent } from '@/types/voiceControl'
import type {
  VoiceAudioInput,
  VoiceIntelligenceAdapter,
  VoiceParseRequest,
  VoiceParseResult,
  VoiceTranscript,
} from '@/types/voiceIntelligence'
import { VoiceIntelligenceError } from '@/types/voiceIntelligence'
import { interpretVoiceText, transcribeVoiceAudio } from '@/api/voiceIntelligence'

const actionIntent: Record<VoiceAction, VoiceIntent> = {
  START: 'MISSION_START',
  PAUSE: 'MISSION_PAUSE',
  RESUME: 'MISSION_RESUME',
  STOP: 'MISSION_STOP',
}

const actionPatterns: Array<[VoiceAction, RegExp]> = [
  ['PAUSE', /暂停|先停一下|暂停任务/u],
  ['RESUME', /继续|恢复(?:任务|执行|运行)?/u],
  ['STOP', /停止|终止|结束任务/u],
  ['START', /开始|启动|执行任务/u],
]

function normalized(text: string) {
  return text.trim().replace(/\s+/gu, '')
}

function notReady(
  request: VoiceParseRequest,
  status: Exclude<VoiceParseResult['status'], 'CANDIDATE'>,
  reason: Exclude<VoiceParseResult, { status: 'CANDIDATE' }>['reason'],
  message: string,
): VoiceParseResult {
  return {
    status,
    requestId: request.requestId,
    reason,
    message,
    normalizedText: normalized(request.text),
    provider: 'local-mock',
    model: 'rules-v1',
  }
}

export function parseMockVoiceIntent(request: VoiceParseRequest): VoiceParseResult {
  const text = normalized(request.text)
  const matched = actionPatterns.filter(([, pattern]) => pattern.test(text)).map(([action]) => action)
  const actions = [...new Set(matched)]

  if (/(攻击|打击|开火|围捕|包围|撤退|返航)/u.test(text)) {
    return notReady(request, 'UNSUPPORTED', 'UNSUPPORTED_CAPABILITY', '该动作尚未接入算法能力，不能生成执行提案。')
  }
  if (/(UAV|USV)[-_]?\d+|(?:第?[一二三四五六七八九十\d]+|某(?:一|个))号?(?:架|艘)?(?:无人机|无人艇)|(?:无人机|无人艇)[-_]?\d+/iu.test(text)) {
    return notReady(request, 'UNSUPPORTED', 'UNSUPPORTED_TARGETING', '当前仅支持整队任务控制，暂不支持指定单台设备。')
  }
  if (/(不要|别|无需|不用|禁止).{0,6}(开始|启动|暂停|继续|恢复|停止|终止|结束)/u.test(text)) {
    return notReady(request, 'NOT_ACTIONABLE', 'NEGATED_ACTION', '检测到否定表达，为避免误执行，请重新明确指令。')
  }
  if (actions.length > 1) {
    return notReady(request, 'NEEDS_CLARIFICATION', 'AMBIGUOUS_ACTION', '一句话中包含多个动作，请一次只说明一个任务动作。')
  }
  if (actions.length === 0) {
    return notReady(request, 'NEEDS_CLARIFICATION', 'NO_SUPPORTED_ACTION', '未识别到开始、暂停、继续或停止，请重新表述。')
  }
  const action = actions[0]!
  if (!request.allowedActions.includes(action)) {
    return notReady(request, 'UNSUPPORTED', 'UNSUPPORTED_CAPABILITY', `当前运行实例未声明 ${action} 能力。`)
  }
  return {
    status: 'CANDIDATE',
    requestId: request.requestId,
    intent: actionIntent[action],
    action,
    normalizedText: text,
    confidence: null,
    provider: 'local-mock',
    model: 'rules-v1',
  }
}

export function createMockVoiceIntelligenceAdapter(mockTranscript = '暂停任务'): VoiceIntelligenceAdapter {
  return {
    name: 'local-mock',
    mode: 'MOCK',
    async transcribe(input: VoiceAudioInput): Promise<VoiceTranscript> {
      if (input.signal?.aborted) throw new VoiceIntelligenceError('请求已取消。', 'VOICE_REQUEST_CANCELLED')
      if (input.audio.size === 0) throw new Error('没有录制到有效音频，请检查麦克风权限后重试。')
      return {
        requestId: input.requestId, text: mockTranscript, locale: input.locale, durationMs: null,
        provider: 'local-mock', model: 'fixed-transcript-v1',
      }
    },
    async parse(input: VoiceParseRequest) {
      return parseMockVoiceIntent(input)
    },
  }
}

export function createBackendVoiceIntelligenceAdapter(): VoiceIntelligenceAdapter {
  return {
    name: 'platform-backend',
    mode: 'BACKEND',
    transcribe: transcribeVoiceAudio,
    parse: interpretVoiceText,
  }
}

const unavailableAdapter: VoiceIntelligenceAdapter = {
  name: 'unconfigured',
  mode: 'BACKEND',
  async transcribe() {
    throw new Error('尚未配置语音识别后端适配器。')
  },
  async parse() {
    throw new Error('尚未配置意图解析后端适配器。')
  },
}

export function createVoiceIntelligenceAdapter(): VoiceIntelligenceAdapter {
  if (import.meta.env.VITE_VOICE_P1_MOCK === 'true') return createMockVoiceIntelligenceAdapter()
  if (import.meta.env.VITE_VOICE_P1_BACKEND === 'true') return createBackendVoiceIntelligenceAdapter()
  return unavailableAdapter
}
