<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Check, Mic2, RefreshCw, ShieldCheck, X } from '@lucide/vue'

import {
  configureVoiceP0MockRuntime,
  setVoiceP0MockOutcome,
  voiceP0MockEnabled,
} from '@/api/voiceControl'
import { useVoiceControlStore } from '@/stores/voiceControl'
import type {
  VoiceAction,
  VoiceIntent,
  VoiceMockOutcome,
  VoiceMockRuntimeHint,
} from '@/types/voiceControl'

const props = defineProps<{ runtimeHint: VoiceMockRuntimeHint }>()
const store = useVoiceControlStore()
const {
  context, proposal, execution, presentationBinding, loading, error, errorCode,
  recoveryPending, recoveryAvailable,
  responseUnknown,
} = storeToRefs(store)
const now = ref(Date.now())
const dialogOpen = ref(false)
const chosenMockOutcome = ref<VoiceMockOutcome>('SUCCESS')
const presentationPendingSince = ref<number | null>(null)
let timer: number | undefined
let pollTick = 0

const actions: Array<{ action: VoiceAction; intent: VoiceIntent; label: string }> = [
  { action: 'START', intent: 'MISSION_START', label: '开始' },
  { action: 'PAUSE', intent: 'MISSION_PAUSE', label: '暂停' },
  { action: 'RESUME', intent: 'MISSION_RESUME', label: '继续' },
  { action: 'STOP', intent: 'MISSION_STOP', label: '停止' },
]
const stateRules: Record<VoiceAction, string[]> = {
  START: ['PREPARED', 'PREVIEW'], PAUSE: ['RUNNING'], RESUME: ['PAUSED'], STOP: ['PREPARED', 'PREVIEW', 'RUNNING', 'PAUSED'],
}
const actionLabels: Record<VoiceAction, string> = { START: '开始任务', PAUSE: '暂停任务', RESUME: '继续任务', STOP: '停止任务' }
const executionLabels: Record<string, string> = {
  QUEUED: '等待调度', DISPATCHED: '已下发', ACCEPTED: '算法已接收', EXECUTING: '算法执行中',
  SUCCEEDED: '算法执行成功', REJECTED: '算法拒绝', FAILED: '算法执行失败',
  INVALIDATED: '执行已失效', TIMED_OUT: '结果未知（超时，仍在查询）',
}
const presentationLabels: Record<string, string> = {
  NOT_REQUIRED: '无需 Unity 同步', PENDING: 'Unity 同步中', REPORTED_APPLIED: 'Unity 已应用', STALE: 'Unity 展示已过期',
}
const errorLabels: Record<string, string> = {
  CONTEXT_CHANGED: '运行上下文、设备集合或展示绑定已变化，请刷新后重新发起。',
  GENERATION_MISMATCH: '场景已重新生成，旧代次不能继续使用。',
  PLAN_MISMATCH: '冻结计划版本或哈希不匹配，请重新创建提案。',
  INVALID_STATE: '当前算法状态不接受该动作。',
  HEARTBEAT_STALE: '算法心跳已失效，暂时不能下发动作。',
  RUNTIME_UNAVAILABLE: '算法进程当前不可用。',
  SCENE_NOT_READY: 'Unity 场景新鲜就绪证据不足。',
  EXECUTION_IN_PROGRESS: '当前实例已有未决执行，未知结果仍会占用执行槽。',
  RUNTIME_BUSY: '独立算法运行槽正在被占用。',
  IDEMPOTENCY_CONFLICT: '幂等键与原请求内容不一致，已停止重试。',
  PROPOSAL_EXPIRED: '提案已过期，请重新创建。',
  PROPOSAL_CANCELLED: '提案已经取消。',
  PROPOSAL_INVALIDATED: '运行条件发生变化，提案已经失效。',
  ALREADY_CONFIRMED: '提案已经确认，不能再取消。',
  UNSUPPORTED_CAPABILITY: '算法实例不支持该动作能力。',
  PROTOCOL_UNSUPPORTED: '当前算法协议不支持 P0 控制。',
  VOICE_CONTROL_DISABLED: '后端尚未启用语音控制 P0 功能开关。',
  ACK_TIMEOUT: '算法回执超时，最终结果仍未知，页面会继续查询。',
}

const secondsLeft = computed(() => proposal.value
  ? Math.max(0, Math.ceil((Date.parse(proposal.value.expiresAt) - now.value) / 1000))
  : 0)
const activeProposal = computed(() => proposal.value?.status === 'AWAITING_CONFIRMATION')
const displayError = computed(() => errorLabels[errorCode.value] ?? error.value)
const heartbeatFresh = computed(() => {
  const heartbeat = context.value?.lastHeartbeatReceivedAt
  return !!heartbeat && now.value - Date.parse(heartbeat) <= 5000
})
const presentationWaitExpired = computed(() => execution.value?.state === 'SUCCEEDED'
  && execution.value.presentationStatus === 'PENDING'
  && presentationPendingSince.value !== null
  && now.value - presentationPendingSince.value >= 30_000)
const contextSummary = computed(() => context.value
  ? `运行 ${context.value.algorithmRunId} · ${context.value.state} · 帧 ${context.value.latestFrameSequence} · 心跳${heartbeatFresh.value ? '正常' : '失效'}`
  : '尚未发现可控制的独立算法实例')

function disabledReason(action: VoiceAction) {
  if (recoveryPending.value || responseUnknown.value) return '请先核对上一次写请求的权威结果'
  if (!context.value) return '没有后端登记的运行实例'
  if (context.value.protocolVersion !== 'algorithm.command.v1') return '旧协议实例不支持 P0 指令'
  if (!context.value.capabilities.includes(action)) return `实例未声明 ${action} 能力`
  if (!stateRules[action].includes(context.value.state)) return `状态 ${context.value.state} 不允许此动作`
  if (!heartbeatFresh.value) return '算法心跳超过 5 秒或尚未建立'
  if (props.runtimeHint.deviceCodes.length === 0) return '尚未生成可冻结的设备集合'
  if (props.runtimeHint.deviceCodes.length > 200) return '设备集合超过 P0 上限 200'
  if ((action === 'START' || action === 'RESUME') && !context.value.sceneReady) return 'Unity 场景尚未就绪'
  if (activeProposal.value || (execution.value && !['SUCCEEDED', 'REJECTED', 'FAILED', 'INVALIDATED'].includes(execution.value.state))) return '请先处理当前指令'
  return ''
}

async function propose(intent: VoiceIntent) {
  await store.propose(intent)
  dialogOpen.value = proposal.value?.status === 'AWAITING_CONFIRMATION'
}

async function confirm() {
  await store.confirm()
  if (execution.value) dialogOpen.value = false
}

async function cancel() {
  if (secondsLeft.value === 0) {
    dialogOpen.value = false
    return
  }
  await store.cancel()
  if (proposal.value?.status === 'CANCELLED') dialogOpen.value = false
}

function setMockOutcome(event: Event) {
  chosenMockOutcome.value = (event.target as HTMLSelectElement).value as VoiceMockOutcome
  setVoiceP0MockOutcome(chosenMockOutcome.value)
}

watch(() => props.runtimeHint, (hint) => {
  configureVoiceP0MockRuntime(hint)
}, { deep: true })

watch(() => props.runtimeHint.algorithmRunId, algorithmRunId => {
  void store.selectAlgorithmRun(algorithmRunId)
}, { immediate: true })

watch(() => [execution.value?.state, execution.value?.presentationStatus], ([state, presentation]) => {
  if (state === 'SUCCEEDED' && presentation === 'PENDING') presentationPendingSince.value ??= Date.now()
  else presentationPendingSince.value = null
}, { immediate: true })

function onVisibilityChange() {
  if (document.visibilityState === 'visible') void store.refreshContexts()
}

onMounted(async () => {
  configureVoiceP0MockRuntime(props.runtimeHint)
  await store.selectAlgorithmRun(props.runtimeHint.algorithmRunId)
  await store.recover()
  timer = window.setInterval(() => {
    now.value = Date.now()
    if (document.visibilityState !== 'visible') return
    pollTick += 1
    if (pollTick % 3 === 0) void store.refreshContexts()
    const timedOutSeconds = execution.value?.timedOutAt
      ? Math.floor((now.value - Date.parse(execution.value.timedOutAt)) / 1000)
      : 0
    const executionDue = execution.value?.state === 'TIMED_OUT'
      ? pollTick % (timedOutSeconds < 30 ? 2 : 10) === 0
      : true
    if (executionDue) void store.poll()
  }, 1000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onBeforeUnmount(() => {
  window.clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <section class="voice-p0">
    <header>
      <div><Mic2 :size="15" /><strong>语音大模型控制 · P0</strong></div>
      <span :class="voiceP0MockEnabled ? 'mock' : 'real'">{{ voiceP0MockEnabled ? '本地 MOCK' : '真实 API' }}</span>
    </header>

    <p class="context-line" :title="contextSummary">
      <i :class="{ online: !!context }"></i>{{ contextSummary }}
    </p>
    <p class="scope-note">当前仅生成“整队任务控制”提案；麦克风、LLM 意图解析和单机控制不属于 P0。</p>
    <p v-if="recoveryPending" class="recovery-note">正在使用原请求内容和原幂等键核对上次未确认的响应……</p>
    <p v-else-if="responseUnknown" class="recovery-note">上次写请求结果未知，不能换新幂等键重发。</p>
    <p v-else-if="!recoveryAvailable" class="error">本地恢复日志不可用，写操作已阻止。</p>
    <p v-if="presentationBinding?.bindingId" class="scope-note" :title="presentationBinding.bindingId">展示绑定已建立；等待 E03 Unity 挑战回执接入。</p>

    <div class="action-grid">
      <button
        v-for="item in actions"
        :key="item.action"
        type="button"
        :disabled="!!disabledReason(item.action) || loading"
        :title="disabledReason(item.action) || `创建${item.label}提案`"
        @click="propose(item.intent)"
      >{{ item.label }}</button>
    </div>

    <label v-if="voiceP0MockEnabled" class="mock-scenario">
      演示结果
      <select :value="chosenMockOutcome" @change="setMockOutcome">
        <option value="SUCCESS">执行成功</option>
        <option value="REJECTED">算法拒绝</option>
        <option value="FAILED">执行失败</option>
        <option value="TIMEOUT_LATE_SUCCESS">超时后迟到成功</option>
      </select>
    </label>

    <article v-if="execution" class="result" :class="execution.outcome.toLowerCase()">
      <div><strong>{{ executionLabels[execution.state] ?? execution.state }}</strong><span>{{ actionLabels[execution.action] }}</span></div>
      <p v-if="execution.errorCode">{{ errorLabels[execution.errorCode] ?? execution.errorCode }}</p>
      <small>算法结果：{{ execution.outcome }} · 展示状态：{{ presentationLabels[execution.presentationStatus] }}</small>
      <p v-if="presentationWaitExpired">算法动作已成功，但 30 秒内暂未收到画面确认；未修改服务端展示状态。</p>
    </article>
    <article v-else-if="proposal && proposal.status !== 'AWAITING_CONFIRMATION'" class="result">
      提案状态：{{ proposal.status }}
    </article>
    <p v-if="displayError" class="error">{{ displayError }}</p>

    <footer>
      <button type="button" @click="store.refreshContexts()"><RefreshCw :size="12" />刷新上下文</button>
      <button v-if="responseUnknown" type="button" @click="store.recover()">核对上次请求</button>
      <button v-if="context" type="button" :title="presentationBinding?.bindingId ?? '尚未建立绑定'" @click="store.takePresentationBinding()">
        {{ presentationBinding?.bindingId ? '重新接管展示' : '建立展示绑定' }}
      </button>
      <button v-if="proposal || execution" type="button" @click="store.clearActive()">清除本地视图</button>
    </footer>
  </section>

  <div v-if="dialogOpen && proposal" class="voice-modal" role="dialog" aria-modal="true" aria-label="确认冻结指令计划">
    <section>
      <header><ShieldCheck :size="18" /><strong>确认冻结计划</strong></header>
      <p>只有点击“确认执行”后才会向算法执行端下发。计划内容不可在此修改。</p>
      <dl>
        <div><dt>动作</dt><dd>{{ actionLabels[proposal.plan.action] }}</dd></div>
        <div><dt>当前仿真</dt><dd>运行 {{ context?.algorithmRunId ?? '-' }} / {{ context?.state ?? '-' }}</dd></div>
        <div><dt>设备快照</dt><dd>{{ proposal.plan.explicitDeviceCodes.length }} 个：{{ proposal.plan.explicitDeviceCodes.join('、') }}</dd></div>
      </dl>
      <details>
        <summary>核对协议身份、版本与哈希</summary>
        <dl>
          <div><dt>运行实例</dt><dd>{{ proposal.plan.runtimeRef }}</dd></div>
          <div><dt>运行代际</dt><dd>{{ proposal.plan.runtimeGeneration }}</dd></div>
          <div><dt>计划版本</dt><dd>v{{ proposal.planVersion }} / {{ proposal.plan.policyVersion }}</dd></div>
          <div><dt>计划哈希</dt><dd class="hash">{{ proposal.planHash }}</dd></div>
        </dl>
      </details>
      <p class="expires">{{ secondsLeft > 0 ? `${secondsLeft} 秒后过期` : '提案已过期，请关闭后重新创建' }}</p>
      <footer>
        <button type="button" :disabled="loading" @click="cancel"><X :size="14" />{{ secondsLeft === 0 ? '关闭' : '取消提案' }}</button>
        <button class="confirm" type="button" :disabled="loading || secondsLeft === 0" @click="confirm"><Check :size="14" />确认执行</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.voice-p0 { display:grid; gap:10px; padding:14px; color:#bddad6; border-bottom:1px solid rgba(108,228,213,.15); background:linear-gradient(145deg,rgba(12,42,47,.95),rgba(5,22,27,.98)); font-size:11px; }
.voice-p0 header,.voice-p0 header div,.voice-p0 footer,.result div { display:flex; align-items:center; justify-content:space-between; gap:7px; }
.voice-p0 header strong { color:#f0fffd; font-size:12px; }
.voice-p0 header span { padding:2px 6px; border:1px solid; border-radius:10px; font-size:9px; font-weight:800; }
.voice-p0 header .mock { color:#ffd58a; border-color:#725b2e; }.voice-p0 header .real { color:#78eadb; border-color:#286c65; }
.context-line,.scope-note,.error,.recovery-note,.result p { margin:0; }.context-line { overflow:hidden; color:#9bc9c3; text-overflow:ellipsis; white-space:nowrap; }
.context-line i { display:inline-block; width:6px; height:6px; margin-right:6px; background:#6a7d7b; border-radius:50%; }.context-line i.online { background:#45db8b; box-shadow:0 0 7px #45db8b; }
.scope-note { color:#6f9691; line-height:1.5; }.action-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.action-grid button,.voice-p0 footer button,.voice-modal button,.mock-scenario select { padding:7px; color:#bce8e1; cursor:pointer; background:#0a282e; border:1px solid #285159; border-radius:4px; font-size:10px; }
.action-grid button:hover:not(:disabled) { color:#061a1e; background:#6ce4d5; }.action-grid button:disabled { cursor:not-allowed; opacity:.35; }
.mock-scenario { display:flex; align-items:center; justify-content:space-between; color:#8fb5b0; }.mock-scenario select { padding:4px 6px; }
.result { padding:9px; border:1px solid #315158; border-radius:4px; background:#081e23; }.result strong { color:#f1fffd; }.result span,.result small { color:#739d98; }.result p,.error { padding-top:5px; color:#ff9d91; line-height:1.45; }
.result.success { border-color:#2a7052; }.voice-p0 footer button { padding:3px 0; background:transparent; border:0; color:#78aaa4; }
.recovery-note { color:#ffd58a; line-height:1.45; }
.voice-modal { position:fixed; inset:0; z-index:1200; display:grid; padding:20px; place-items:center; background:rgba(0,8,11,.78); backdrop-filter:blur(4px); }
.voice-modal > section { width:min(560px,100%); padding:20px; color:#b9d8d4; background:#071b20; border:1px solid #3d746f; border-radius:7px; box-shadow:0 24px 80px #000; }
.voice-modal header,.voice-modal footer { display:flex; align-items:center; gap:9px; }.voice-modal header { color:#effffd; }.voice-modal p { color:#86aca7; font-size:12px; line-height:1.5; }
.voice-modal dl { display:grid; gap:1px; margin:15px 0; background:#18353a; border:1px solid #18353a; }.voice-modal dl div { display:grid; padding:8px 10px; background:#0a2429; grid-template-columns:92px 1fr; }
.voice-modal dt { color:#779e99; }.voice-modal dd { min-width:0; margin:0; color:#d8eeeb; word-break:break-all; }.voice-modal .hash { font:10px Consolas,monospace; }
.voice-modal details { margin:10px 0; }.voice-modal summary { color:#79beb5; cursor:pointer; font-size:11px; }.voice-modal details dl { margin-top:8px; }
.voice-modal .expires { color:#ffd58a; }.voice-modal footer { justify-content:flex-end; }.voice-modal button.confirm { color:#04191b; background:#6ce4d5; border-color:#6ce4d5; }.voice-modal button:disabled { opacity:.4; }
</style>
