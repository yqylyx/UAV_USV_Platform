import { ref, shallowRef } from 'vue'
import type SimulationUnityWebglPanel from '@/components/unity/SimulationUnityWebglPanel.vue'
import type { UnityWindowMessage } from '@/utils/unityWebglProtocol'

export type SimulationTacticalNotice = {
  eventId: string
  type: string
  threatCode?: string
  title: string
  message: string
  confidence?: number
  sequence?: number
}

const pendingNotices: SimulationTacticalNotice[] = []
let noticeTimer: ReturnType<typeof setTimeout> | undefined
let appliedSequence = 0
let noticesVisible = false
const noticeCopy: Record<string, string> = {
  ATTACK_INTENT_CONFIRMED: '发现攻击意图 · 启动守卫响应',
  GUARD_RESPONSE_DISPATCHED: '守卫组已出动 · 分向建立屏障',
  GUARD_SCREEN_ESTABLISHED: '守卫屏障已建立 · 阻断攻击通道',
  COVER_RETREAT_OBSERVED: '朝敌倒航 · 正在守卫',
  DEFENSE_HANDOFF_CONFIRMED: '分向守卫完成 · 转入协同拦截',
  PROTECTED_WITHDRAWAL_CONFIRMED: '目标已安全撤出 · 转入前出拦截',
  ESCAPE_INTENT_CONFIRMED: '发现逃逸意图 · 切换协同追击',
}

function displayNextNotice() {
  noticeTimer = undefined
  if (!noticesVisible || simulationRuntime.recovering.value) return
  const next = pendingNotices[0]
  if (!next || (next.sequence ?? 0) > appliedSequence) return
  pendingNotices.shift()
  simulationRuntime.tacticalNotices.value = [next]
  noticeTimer = setTimeout(() => {
    simulationRuntime.tacticalNotices.value = []
    noticeTimer = setTimeout(() => {
      noticeTimer = undefined
      showNextNotice()
    }, 300)
  }, 3500)
}

function showNextNotice() {
  if (noticeTimer || !noticesVisible || simulationRuntime.recovering.value) return
  const next = pendingNotices[0]
  if (!next || (next.sequence ?? 0) > appliedSequence) return
  // Briefly collect adjacent runtime frames, e.g. two teams departing one
  // tick apart. Never show the second incident before its Unity receipt.
  noticeTimer = setTimeout(displayNextNotice, 600)
}

export function enqueueTacticalNotices(events: SimulationTacticalNotice[]) {
  for (const event of events) {
    // Screen establishment remains in the event history. A second toast for
    // it only delays the physically observed withdrawal notice behind actions
    // that have already finished.
    if (event.type === 'GUARD_SCREEN_ESTABLISHED') continue
    const superseded: Record<string, string[]> = {
      COVER_RETREAT_OBSERVED: ['GUARD_RESPONSE_DISPATCHED'],
      PROTECTED_WITHDRAWAL_CONFIRMED: ['GUARD_RESPONSE_DISPATCHED', 'COVER_RETREAT_OBSERVED'],
      DEFENSE_HANDOFF_CONFIRMED: ['GUARD_RESPONSE_DISPATCHED', 'COVER_RETREAT_OBSERVED'],
      ESCAPE_INTENT_CONFIRMED: ['GUARD_RESPONSE_DISPATCHED', 'COVER_RETREAT_OBSERVED', 'PROTECTED_WITHDRAWAL_CONFIRMED'],
    }
    for (let index = pendingNotices.length - 1; index >= 0; index--) {
      const pending = pendingNotices[index]!
      if (!superseded[event.type]?.includes(pending.type)) continue
      const remaining = (pending.threatCode?.split(' / ') ?? []).filter(code => code !== event.threatCode)
      if (remaining.length) pending.threatCode = remaining.join(' / ')
      else pendingNotices.splice(index, 1)
    }
    // Merge concurrent incidents for presentation, retaining each raw event
    // in history. The queue still preserves attack -> departure -> screen.
    const sibling = pendingNotices.find(item => item.type === event.type
      && Math.abs((item.sequence ?? 0) - (event.sequence ?? 0)) <= 30)
    if (sibling) {
      sibling.threatCode = [...new Set([...(sibling.threatCode?.split(' / ') ?? []), event.threatCode].filter(Boolean))].join(' / ')
      sibling.sequence = Math.max(sibling.sequence ?? 0, event.sequence ?? 0)
      sibling.confidence = Math.min(sibling.confidence ?? 1, event.confidence ?? 1)
    } else {
      pendingNotices.push({ ...event, title: noticeCopy[event.type] ?? event.title })
    }
  }
  showNextNotice()
}

export function acknowledgeTacticalFrame(sequence: number) {
  appliedSequence = Math.max(appliedSequence, sequence)
  showNextNotice()
}

export function setTacticalNoticesVisible(visible: boolean) {
  noticesVisible = visible
  if (!visible) {
    clearTimeout(noticeTimer)
    noticeTimer = undefined
    simulationRuntime.tacticalNotices.value = []
  } else showNextNotice()
}

export function resetTacticalNotices() {
  clearTimeout(noticeTimer)
  noticeTimer = undefined
  pendingNotices.length = 0
  appliedSequence = 0
  simulationRuntime.tacticalNotices.value = []
  simulationRuntime.tacticalHistory.value = []
}

// One simulation owner, independent of the real-device runtime. The view owns
// business state; App owns the iframe DOM so KeepAlive cannot detach it.
export const simulationRuntime = {
  requested: ref(false),
  recovering: ref(false),
  recoveryError: ref(''),
  tacticalNotices: ref<SimulationTacticalNotice[]>([]),
  tacticalHistory: ref<SimulationTacticalNotice[]>([]),
  panel: shallowRef<InstanceType<typeof SimulationUnityWebglPanel> | null>(null),
  events: null as null | {
    ready: () => void
    loading: () => void
    message: (message: UnityWindowMessage) => void
    error: (message: string) => void
  },
}
