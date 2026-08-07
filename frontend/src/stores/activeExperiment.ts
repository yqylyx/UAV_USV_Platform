import { defineStore } from 'pinia'
import type { MissionDetail, MissionStatus } from '@/types/mission'

type ExperimentSnapshot = {
  missionId: number | null
  runId: number | null
  runNo: number | null
  algorithmCode: string
  status: MissionStatus | 'IDLE'
  phase: string
}

const STORAGE_KEY = 'uav-usv:active-experiment'

function restore(): ExperimentSnapshot {
  const fallback: ExperimentSnapshot = { missionId: null, runId: null, runNo: null, algorithmCode: '', status: 'IDLE', phase: 'PREPARE' }
  if (typeof window === 'undefined') return fallback
  try {
    return { ...fallback, ...JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}') }
  } catch {
    return fallback
  }
}

export const useActiveExperimentStore = defineStore('active-experiment', {
  state: restore,
  getters: {
    running: state => state.status === 'RUNNING' || state.status === 'PAUSED',
    label: state => state.runNo ? `RUN ${state.runNo}` : '尚未执行',
  },
  actions: {
    persist() {
      if (typeof window !== 'undefined') window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(this.$state))
    },
    sync(detail: MissionDetail) {
      this.missionId = detail.mission.id
      this.runId = detail.currentRun?.id ?? null
      this.runNo = detail.currentRun?.runNo ?? null
      this.algorithmCode = detail.currentRun?.algorithmCode || detail.mission.algorithmCode
      this.status = detail.mission.status
      this.phase = detail.currentRun?.stage || detail.mission.stage
      this.persist()
    },
    updatePhase(phase: string) {
      this.phase = phase
      this.persist()
    },
  },
})
