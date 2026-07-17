import { defineStore } from 'pinia'

export type UnityViewportTarget = 'dashboard' | 'mission-execution' | null

export const useUnityViewportStore = defineStore('unityViewport', {
  state: () => ({
    target: null as UnityViewportTarget,
    missionInstanceId: `mission-unity-${Date.now()}`,
    missionId: null as number | null,
    runId: null as number | null,
  }),
  actions: {
    show(target: Exclude<UnityViewportTarget, null>) {
      this.target = target
    },
    park() {
      this.target = null
    },
    prepareMission(missionId: number | null, runId: number | null = null, instanceId?: string | null) {
      this.missionId = missionId
      this.runId = runId
      if (instanceId) this.missionInstanceId = instanceId
    },
    createMissionInstance(missionId: number) {
      this.missionInstanceId = `mission-unity-${Date.now()}`
      this.missionId = missionId
      this.runId = null
      this.target = null
      return this.missionInstanceId
    },
    bindRun(runId: number | null) {
      this.runId = runId
    },
  },
})
