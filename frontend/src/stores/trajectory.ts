import { defineStore } from 'pinia'
import type { UnityRuntimeScope } from './unityBridge'

export type TrajectoryAgentType = 'UAV' | 'USV' | 'TARGET'

export interface UnityTrajectoryAgent {
  code: string
  type: TrajectoryAgentType
  x: number
  y: number
  z: number
  yaw: number
  state: string
}

export interface UnityTrajectoryMission {
  phase: string
  elapsed: number
  captureRadius: number
  defenseRadius: number
  captureReady: boolean
  formationHolding: boolean
}

export interface UnityTrajectoryFrame {
  sequence: number
  source: string
  coordinateSystem: string
  mission: UnityTrajectoryMission
  agents: UnityTrajectoryAgent[]
  receivedAt: number
}

interface TrajectoryChannel {
  frame: UnityTrajectoryFrame | null
  lastSequence: number
}

function finite(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export const useTrajectoryStore = defineStore('trajectory', {
  state: () => ({
    channels: {
      SYSTEM_OVERVIEW: { frame: null, lastSequence: 0 },
      MISSION_CENTER: { frame: null, lastSequence: 0 },
    } as Record<UnityRuntimeScope, TrajectoryChannel>,
  }),
  getters: {
    frame: (state) => state.channels.SYSTEM_OVERVIEW.frame,
    lastSequence: (state) => state.channels.SYSTEM_OVERVIEW.lastSequence,
    isLive: (state) => {
      const frame = state.channels.SYSTEM_OVERVIEW.frame
      return !!frame && Date.now() - frame.receivedAt <= 2000
    },
    frameFor: (state) => (scope: UnityRuntimeScope) => state.channels[scope].frame,
    isLiveFor: (state) => (scope: UnityRuntimeScope) => {
      const frame = state.channels[scope].frame
      return !!frame && Date.now() - frame.receivedAt <= 2000
    },
  },
  actions: {
    ingestFor(scope: UnityRuntimeScope, payload: Record<string, unknown>) {
      const channel = this.channels[scope]
      const sequence = finite(payload.sequence)
      const sequenceRestarted = sequence > 0 && sequence <= 3 && sequence < channel.lastSequence
      if (sequenceRestarted) {
        channel.frame = null
        channel.lastSequence = 0
      }
      if (sequence <= channel.lastSequence) return
      const mission = (payload.mission ?? {}) as Record<string, unknown>
      const agents = Array.isArray(payload.agents) ? payload.agents : []
      const normalizedAgents = agents
        .map((item) => item as Record<string, unknown>)
        .filter((item) => ['UAV', 'USV', 'TARGET'].includes(String(item.type)))
        .map((item) => ({
          code: String(item.code ?? '').trim().toLowerCase(),
          type: String(item.type) as TrajectoryAgentType,
          x: finite(item.x),
          y: finite(item.y),
          z: finite(item.z),
          yaw: finite(item.yaw),
          state: String(item.state ?? 'UNKNOWN'),
        }))
        .filter((item) => item.code)
      if (!normalizedAgents.some((item) => item.type === 'TARGET')) return

      channel.lastSequence = sequence
      channel.frame = {
        sequence,
        source: String(payload.source ?? 'unity-webgl'),
        coordinateSystem: String(payload.coordinateSystem ?? 'UNITY_XZ'),
        mission: {
          phase: String(mission.phase ?? '等待任务阶段'),
          elapsed: finite(mission.elapsed),
          captureRadius: Math.max(0.1, finite(mission.captureRadius)),
          defenseRadius: Math.max(0.1, finite(mission.defenseRadius)),
          captureReady: mission.captureReady === true,
          formationHolding: mission.formationHolding === true,
        },
        agents: normalizedAgents,
        receivedAt: Date.now(),
      }
    },
    ingest(payload: Record<string, unknown>) {
      this.ingestFor('SYSTEM_OVERVIEW', payload)
    },
    clearFor(scope: UnityRuntimeScope) {
      this.channels[scope].frame = null
      this.channels[scope].lastSequence = 0
    },
    clear() {
      this.clearFor('SYSTEM_OVERVIEW')
    },
  },
})
