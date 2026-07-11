import { defineStore } from 'pinia'

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

function finite(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

export const useTrajectoryStore = defineStore('trajectory', {
  state: () => ({
    frame: null as UnityTrajectoryFrame | null,
    lastSequence: 0,
  }),
  getters: {
    isLive: (state) => !!state.frame && Date.now() - state.frame.receivedAt <= 2000,
  },
  actions: {
    ingest(payload: Record<string, unknown>) {
      const sequence = finite(payload.sequence)
      if (sequence <= this.lastSequence) return
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

      this.lastSequence = sequence
      this.frame = {
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
    clear() {
      this.frame = null
      this.lastSequence = 0
    },
  },
})
