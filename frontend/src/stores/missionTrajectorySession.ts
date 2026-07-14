import { defineStore } from 'pinia'

export type MissionTrajectorySessionState =
  | 'IDLE'
  | 'DEPLOYING'
  | 'READY'
  | 'RUNNING'
  | 'PAUSED'
  | 'RETURNING'
  | 'STOPPED'

export type MissionCommandSource = 'MISSION_CONTROL' | 'SYSTEM_OVERVIEW'

const storageKey = 'uav-usv:mission-trajectory-session'

type StoredTrajectorySession = {
  missionId: number | null
  runId: number | null
  state: MissionTrajectorySessionState
  source: MissionCommandSource | null
  startSequence: number | null
}

function restoredSession(): StoredTrajectorySession {
  const fallback: StoredTrajectorySession = { missionId: null, runId: null, state: 'IDLE', source: null, startSequence: null }
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.sessionStorage.getItem(storageKey)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<StoredTrajectorySession>
    const states: MissionTrajectorySessionState[] = ['IDLE', 'DEPLOYING', 'READY', 'RUNNING', 'PAUSED', 'RETURNING', 'STOPPED']
    if (!parsed.state || !states.includes(parsed.state)) return fallback
    return {
      missionId: typeof parsed.missionId === 'number' ? parsed.missionId : null,
      runId: typeof parsed.runId === 'number' ? parsed.runId : null,
      state: parsed.state,
      source: parsed.source === 'MISSION_CONTROL' || parsed.source === 'SYSTEM_OVERVIEW' ? parsed.source : null,
      startSequence: typeof parsed.startSequence === 'number' ? parsed.startSequence : null,
    }
  } catch {
    return fallback
  }
}

const restored = restoredSession()

export const useMissionTrajectorySessionStore = defineStore('missionTrajectorySession', {
  state: () => ({
    missionId: restored.missionId,
    runId: restored.runId,
    state: restored.state,
    source: restored.source,
    startSequence: restored.startSequence,
    revision: 0,
  }),
  getters: {
    recording: (state) => state.state === 'RUNNING' || state.state === 'RETURNING',
    locallyControlled: (state) => state.source === 'MISSION_CONTROL' && state.state !== 'IDLE',
    controlsMission: (state) => state.source === 'MISSION_CONTROL' && ['DEPLOYING', 'READY', 'RUNNING', 'PAUSED', 'RETURNING'].includes(state.state),
  },
  actions: {
    persist() {
      if (typeof window === 'undefined') return
      try {
        window.sessionStorage.setItem(storageKey, JSON.stringify({
          missionId: this.missionId,
          runId: this.runId,
          state: this.state,
          source: this.source,
          startSequence: this.startSequence,
        }))
      } catch {
        // The in-memory session remains authoritative if storage is unavailable.
      }
    },
    bind(missionId: number | null, runId: number | null) {
      if (this.missionId === missionId) {
        this.runId = runId
        this.persist()
        return
      }
      this.missionId = missionId
      this.runId = runId
      this.state = 'IDLE'
      this.source = null
      this.startSequence = null
      this.revision += 1
      this.persist()
    },
    beginDeployment(sequence: number) {
      this.state = 'DEPLOYING'
      this.source = 'MISSION_CONTROL'
      this.startSequence = Math.max(0, sequence)
      this.revision += 1
      this.persist()
    },
    markReady(sequence: number) {
      this.state = 'READY'
      this.source = 'MISSION_CONTROL'
      this.startSequence = Math.max(0, sequence)
      this.persist()
    },
    start(sequence: number, runId?: number | null) {
      this.state = 'RUNNING'
      this.source = 'MISSION_CONTROL'
      if (runId !== undefined) this.runId = runId
      this.startSequence = Math.max(0, sequence)
      this.revision += 1
      this.persist()
    },
    pause() {
      if (this.source === 'MISSION_CONTROL' && (this.state === 'RUNNING' || this.state === 'RETURNING')) {
        this.state = 'PAUSED'
        this.persist()
      }
    },
    resume(sequence: number) {
      if (this.source !== 'MISSION_CONTROL' || this.state !== 'PAUSED') return
      this.state = 'RUNNING'
      this.startSequence = Math.max(0, sequence)
      this.persist()
    },
    beginReturn(sequence: number) {
      if (this.source !== 'MISSION_CONTROL') return
      this.state = 'RETURNING'
      this.startSequence = Math.max(0, sequence)
      this.persist()
    },
    stop() {
      if (this.source !== 'MISSION_CONTROL') return
      this.state = 'STOPPED'
      this.persist()
    },
    reset() {
      this.state = 'IDLE'
      this.source = null
      this.startSequence = null
      this.revision += 1
      this.persist()
    },
  },
})
