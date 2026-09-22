<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Mic, Square, WandSparkles } from '@lucide/vue'

import { createVoiceIntelligenceAdapter } from '@/services/voiceIntelligence'
import type { VoiceAction, VoiceIntent } from '@/types/voiceControl'
import type { VoiceInputStage, VoiceIntelligenceAdapter, VoiceParseResult } from '@/types/voiceIntelligence'

const props = withDefaults(defineProps<{
  adapter?: VoiceIntelligenceAdapter
  allowedActions: VoiceAction[]
  deviceCodes: string[]
  submissionDisabled?: boolean
  actionDisabledReason?: (action: VoiceAction) => string
}>(), { adapter: undefined, submissionDisabled: false, actionDisabledReason: undefined })
const emit = defineEmits<{ candidate: [intent: VoiceIntent] }>()

const adapter = props.adapter ?? createVoiceIntelligenceAdapter()
const draft = ref('')
const stage = ref<VoiceInputStage>('IDLE')
const result = ref<VoiceParseResult | null>(null)
const message = ref('可直接输入文字；语音识别结果也会先放入此处供人工修改。')
let recorder: MediaRecorder | null = null
let stream: MediaStream | null = null
let chunks: Blob[] = []

const busy = computed(() => ['TRANSCRIBING', 'PARSING'].includes(stage.value))
const candidate = computed(() => result.value?.status === 'CANDIDATE' ? result.value : null)
const candidateDisabledReason = computed(() => candidate.value && props.actionDisabledReason
  ? props.actionDisabledReason(candidate.value.action)
  : '')
const statusLabel = computed(() => ({
  IDLE: '等待输入', RECORDING: '正在录音', TRANSCRIBING: '正在识别', READY_TO_PARSE: '待解析',
  PARSING: '正在解析', CANDIDATE: '候选指令', NEEDS_CLARIFICATION: '需要澄清',
  UNSUPPORTED: '暂不支持', ERROR: '处理失败',
}[stage.value]))

watch(draft, () => {
  if (!['RECORDING', 'TRANSCRIBING', 'PARSING'].includes(stage.value)) {
    result.value = null
    stage.value = draft.value.trim() ? 'READY_TO_PARSE' : 'IDLE'
    message.value = '文字可以继续修改；解析只生成候选，不会直接执行。'
  }
})

function stopTracks() {
  stream?.getTracks().forEach(track => track.stop())
  stream = null
}

async function startRecording() {
  result.value = null
  message.value = ''
  try {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error('当前浏览器不支持麦克风录音，请改用文字输入。')
    }
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    recorder = new MediaRecorder(stream)
    recorder.addEventListener('dataavailable', event => { if (event.data.size > 0) chunks.push(event.data) })
    recorder.addEventListener('stop', () => { void transcribeRecording() }, { once: true })
    recorder.start()
    stage.value = 'RECORDING'
    message.value = '录音仅在当前页面暂存；停止后交给已配置的识别适配器。'
  } catch (error) {
    stopTracks()
    stage.value = 'ERROR'
    message.value = error instanceof Error ? error.message : '无法启动录音。'
  }
}

function stopRecording() {
  if (recorder?.state === 'recording') recorder.stop()
}

async function transcribeRecording() {
  stage.value = 'TRANSCRIBING'
  stopTracks()
  try {
    const audio = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
    const transcript = await adapter.transcribe({ audio, locale: 'zh-CN', requestId: crypto.randomUUID() })
    draft.value = transcript.text
    stage.value = 'READY_TO_PARSE'
    message.value = `识别结果来自 ${transcript.provider}；请核对文字后再解析。`
  } catch (error) {
    stage.value = 'ERROR'
    message.value = error instanceof Error ? error.message : '语音识别失败。'
  } finally {
    recorder = null
    chunks = []
  }
}

async function parseDraft() {
  if (!draft.value.trim()) {
    stage.value = 'NEEDS_CLARIFICATION'
    message.value = '请先输入或录制一条指令。'
    return
  }
  stage.value = 'PARSING'
  result.value = null
  try {
    const parsed = await adapter.parse({
      requestId: crypto.randomUUID(), text: draft.value, locale: 'zh-CN',
      allowedActions: props.allowedActions, availableDeviceCodes: props.deviceCodes,
    })
    result.value = parsed
    stage.value = parsed.status === 'NOT_ACTIONABLE' ? 'NEEDS_CLARIFICATION' : parsed.status
    message.value = parsed.status === 'CANDIDATE'
      ? `已解析为 ${parsed.action}；仍需生成并确认后端冻结提案。`
      : parsed.message
  } catch (error) {
    stage.value = 'ERROR'
    message.value = error instanceof Error ? error.message : '意图解析失败。'
  }
}

function submitCandidate() {
  if (!candidate.value || props.submissionDisabled || candidateDisabledReason.value) return
  emit('candidate', candidate.value.intent)
}

onBeforeUnmount(() => {
  if (recorder?.state === 'recording') recorder.stop()
  stopTracks()
})
</script>

<template>
  <section class="intelligence-input" aria-label="语音与文本指令输入">
    <header>
      <strong>语音 / 文本指令</strong>
      <span :class="adapter.mode.toLowerCase()">{{ adapter.mode === 'MOCK' ? '解析 MOCK' : '待接后端' }}</span>
    </header>
    <textarea v-model="draft" rows="3" maxlength="200" placeholder="例如：暂停当前任务" :disabled="busy || stage === 'RECORDING'" />
    <div class="controls">
      <button v-if="stage !== 'RECORDING'" type="button" :disabled="busy" @click="startRecording">
        <Mic :size="13" />开始录音
      </button>
      <button v-else class="recording" type="button" @click="stopRecording"><Square :size="12" />停止录音</button>
      <button type="button" :disabled="busy || stage === 'RECORDING' || !draft.trim()" @click="parseDraft">
        <WandSparkles :size="13" />解析指令
      </button>
    </div>
    <p class="status"><b>{{ statusLabel }}</b><span>{{ message }}</span></p>
    <article v-if="candidate" class="candidate">
      <div><strong>{{ candidate.action }}</strong><small>{{ candidate.intent }}</small></div>
      <p>候选结果不会直接执行；下一步仍进入冻结提案和人工确认。</p>
      <button type="button" :disabled="submissionDisabled || !!candidateDisabledReason" :title="candidateDisabledReason" @click="submitCandidate">
        {{ candidateDisabledReason || '生成待确认提案' }}
      </button>
    </article>
  </section>
</template>

<style scoped>
.intelligence-input { display:grid; gap:8px; padding:10px; background:#071e23; border:1px solid rgba(108,228,213,.2); border-radius:5px; }
.intelligence-input header,.controls,.candidate div { display:flex; align-items:center; justify-content:space-between; gap:7px; }
.intelligence-input header strong { color:#eafffc; font-size:11px; }.intelligence-input header span { padding:2px 5px; border:1px solid #42615f; border-radius:8px; color:#8db0ac; font-size:8px; }
.intelligence-input header span.mock { color:#ffd58a; border-color:#725b2e; }
textarea { box-sizing:border-box; width:100%; resize:vertical; padding:8px; color:#d9f1ed; background:#06191e; border:1px solid #28484e; border-radius:4px; font:10px/1.5 inherit; }
textarea:focus { outline:1px solid #58bfb3; border-color:#58bfb3; }.controls button,.candidate button { display:inline-flex; align-items:center; justify-content:center; gap:4px; padding:6px 8px; color:#aedad4; cursor:pointer; background:#0a282e; border:1px solid #285159; border-radius:4px; font-size:9px; }
.controls button { flex:1; }.controls button.recording { color:#ffb3aa; border-color:#8b453f; }.controls button:disabled,.candidate button:disabled { cursor:not-allowed; opacity:.35; }
.status { display:grid; gap:2px; margin:0; color:#709792; line-height:1.4; }.status b { color:#93c4be; font-size:9px; }.status span { font-size:9px; }
.candidate { display:grid; gap:6px; padding:8px; background:#082329; border:1px solid #2a7052; border-radius:4px; }.candidate strong { color:#78eadb; }.candidate small { color:#709792; }.candidate p { margin:0; color:#86aca7; font-size:9px; line-height:1.4; }.candidate button { color:#04191b; background:#6ce4d5; border-color:#6ce4d5; }
</style>
