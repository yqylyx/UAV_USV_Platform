import { defineStore } from 'pinia'

import { useActiveExperimentStore } from '@/stores/activeExperiment'
import { useRealtimeStore } from '@/stores/realtime'
import {
  isPoseBatchLive,
  isRealtimeEnvelopeApplicable,
  type RealtimeRunScopePolicy,
} from '@/services/realtimeTrajectoryAdapter'
import type { MissionStatus } from '@/types/mission'

export type RealMissionRuntimeState =
  | 'IDLE'
  | 'READY'
  | 'STARTING'
  | 'RUNNING'
  | 'CANCELLING'
  | 'CANCELLED'
  | 'FAILED'
  | 'COMPLETED'

type LifecycleAction = 'START' | 'CANCEL' | null

type RuntimeContext = {
  missionId?: number | null
  runId?: number | null
  backendMissionStatus?: MissionStatus | null
  runScopePolicy?: RealtimeRunScopePolicy
}

const terminalStates = new Set(['CANCELLED', 'FAILED', 'COMPLETED'])
const runningStates = new Set(['RUNNING', 'EXECUTING', 'ACTIVE', 'STARTED', 'ENCIRCLING'])
const runningPhases = new Set([
  'ENCIRCLING',
  'FORMATION_CONVERGING',
  'ENCIRCLEMENT',
  'CAPTURE',
  'CAPTURING',
  'CAPTURED',
  'PURSUIT',
  'TASK_RUNNING',
])
const failedCommandStates = new Set(['FAILED', 'REJECTED', 'TIMEOUT', 'EXPIRED'])

function normalizeState(value: unknown) {
  return String(value ?? '').trim().toUpperCase()
}

function terminalRuntimeState(value: unknown): RealMissionRuntimeState | null {
  const state = normalizeState(value)
  if (state === 'SUCCESS' || state === 'SUCCEEDED') return 'COMPLETED'
  if (state === 'ABORTED') return 'CANCELLED'
  if (terminalStates.has(state)) return state as RealMissionRuntimeState
  return null
}

function commandStatus(commandKey: string, statuses: Record<string, string>) {
  return normalizeState(commandKey ? statuses[commandKey] : '')
}

export const useRealMissionRuntimeStore = defineStore('realMissionRuntime', {
  state: () => ({
    missionId: null as number | null,
    runId: null as number | null,
    syncedBackendMissionStatus: null as MissionStatus | null,
    runScopePolicy: 'ALLOW_MISSING' as RealtimeRunScopePolicy,
    lastStartCommandKey: '',
    lastCancelCommandKey: '',
    lifecycleAction: null as LifecycleAction,
    suppressedRosTerminalKey: '',
  }),
  getters: {
    currentMissionId(state) {
      const activeExperimentStore = useActiveExperimentStore()
      return state.missionId ?? activeExperimentStore.missionId
    },
    currentRunId(state) {
      const activeExperimentStore = useActiveExperimentStore()
      return state.runId ?? activeExperimentStore.runId
    },
    currentBackendMissionStatus(state) {
      const activeExperimentStore = useActiveExperimentStore()
      return state.syncedBackendMissionStatus ?? (
        activeExperimentStore.status === 'IDLE' ? null : activeExperimentStore.status
      )
    },
    backendMissionStatus(): MissionStatus | null {
      return this.currentBackendMissionStatus
    },
    poseLive(state) {
      const realtimeStore = useRealtimeStore()
      const activeExperimentStore = useActiveExperimentStore()
      const currentRunId = state.runId ?? activeExperimentStore.runId
      return realtimeStore.connected
        && isRealtimeEnvelopeApplicable(
          realtimeStore.poseBatch,
          { runId: currentRunId },
          state.runScopePolicy,
        )
        && isPoseBatchLive(realtimeStore.poseBatch)
    },
    runtimeState(state): RealMissionRuntimeState {
      const realtimeStore = useRealtimeStore()
      const activeExperimentStore = useActiveExperimentStore()
      const currentRunId = state.runId ?? activeExperimentStore.runId
      const backendStatus = normalizeState(this.currentBackendMissionStatus)
      const missionStatus = isRealtimeEnvelopeApplicable(
        realtimeStore.missionStatus,
        { runId: currentRunId },
        state.runScopePolicy,
      )
        ? realtimeStore.missionStatus?.payload
        : null
      const rosState = normalizeState(missionStatus?.state)
      const rosPhase = normalizeState(missionStatus?.phase)
      const rosTerminalKey = [
        this.currentMissionId ?? 'missing-mission',
        currentRunId ?? 'missing-run',
        rosState,
        rosPhase,
      ].join(':')
      const startStatus = commandStatus(state.lastStartCommandKey, realtimeStore.commandStatuses)
      const cancelStatus = commandStatus(state.lastCancelCommandKey, realtimeStore.commandStatuses)

      const backendTerminal = terminalRuntimeState(backendStatus)
      if (backendTerminal) return backendTerminal
      const rosTerminal = terminalRuntimeState(rosState) ?? terminalRuntimeState(rosPhase)
      if (
        rosTerminal
        && !(backendStatus === 'READY' && state.suppressedRosTerminalKey === rosTerminalKey)
      ) {
        return rosTerminal
      }

      if (
        state.lifecycleAction === 'CANCEL'
        && !terminalRuntimeState(cancelStatus)
        && !failedCommandStates.has(cancelStatus)
      ) {
        return 'CANCELLING'
      }

      if (
        startStatus === 'EXECUTING'
        || runningStates.has(rosState)
        || runningPhases.has(rosPhase)
      ) {
        return 'RUNNING'
      }

      if (backendStatus === 'RUNNING' || backendStatus === 'PAUSED') return 'RUNNING'

      if (
        state.lifecycleAction === 'START'
        || startStatus === 'ACCEPTED'
        || startStatus === 'PENDING'
        || startStatus === 'DISPATCHED'
      ) {
        if (!failedCommandStates.has(startStatus)) return 'STARTING'
      }

      if (backendStatus === 'READY') return 'READY'
      return 'IDLE'
    },
    canStart(): boolean {
      return this.runtimeState === 'READY'
    },
    canCancel(): boolean {
      return this.runtimeState === 'RUNNING'
    },
    canRetry(): boolean {
      return terminalStates.has(this.runtimeState)
    },
    isRunning(): boolean {
      return this.runtimeState === 'RUNNING'
    },
    isTerminal(): boolean {
      return terminalStates.has(this.runtimeState)
    },
  },
  actions: {
    syncContext(context: RuntimeContext) {
      const previousRunId = this.runId
      if (context.missionId !== undefined) this.missionId = context.missionId
      if (context.runId !== undefined) this.runId = context.runId
      if (context.backendMissionStatus !== undefined) this.syncedBackendMissionStatus = context.backendMissionStatus
      if (context.runScopePolicy !== undefined) this.runScopePolicy = context.runScopePolicy
      if (context.runId !== undefined && context.runId !== previousRunId) {
        this.lastStartCommandKey = ''
        this.lastCancelCommandKey = ''
        this.lifecycleAction = null
        this.suppressedRosTerminalKey = ''
      }
      if (terminalRuntimeState(context.backendMissionStatus)) {
        this.lifecycleAction = null
      }
    },
    noteStartCommand(commandKey: string) {
      this.lastStartCommandKey = commandKey
      this.lifecycleAction = 'START'
      this.suppressedRosTerminalKey = ''
    },
    noteCancelCommand(commandKey: string) {
      this.lastCancelCommandKey = commandKey
      this.lifecycleAction = 'CANCEL'
      this.suppressedRosTerminalKey = ''
    },
    acknowledgeTerminalForRetry() {
      const realtimeStore = useRealtimeStore()
      const activeExperimentStore = useActiveExperimentStore()
      const currentRunId = this.runId ?? activeExperimentStore.runId
      const missionStatus = isRealtimeEnvelopeApplicable(
        realtimeStore.missionStatus,
        { runId: currentRunId },
        this.runScopePolicy,
      )
        ? realtimeStore.missionStatus?.payload
        : null
      const rosState = normalizeState(missionStatus?.state)
      const rosPhase = normalizeState(missionStatus?.phase)
      if (terminalRuntimeState(rosState) || terminalRuntimeState(rosPhase)) {
        this.suppressedRosTerminalKey = [
          this.currentMissionId ?? 'missing-mission',
          currentRunId ?? 'missing-run',
          rosState,
          rosPhase,
        ].join(':')
      }
      this.lastStartCommandKey = ''
      this.lastCancelCommandKey = ''
      this.lifecycleAction = null
    },
    clearLifecycleAction() {
      this.lifecycleAction = null
    },
  },
})
