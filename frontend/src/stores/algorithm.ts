import { defineStore } from 'pinia'

import {
  fetchAlgorithmAssignments,
  fetchAlgorithmEvents,
  fetchAlgorithmStatus,
  startAlgorithm,
  stopAlgorithm,
  type AlgorithmAssignments,
  type AlgorithmEvent,
  type AlgorithmRun,
  type AlgorithmStartPayload,
  type AlgorithmStopPayload,
} from '@/api/algorithm'

interface State {
  runs: AlgorithmRun[]
  assignments: AlgorithmAssignments | null
  events: AlgorithmEvent[]
  loading: boolean
  error: string
}

export const useAlgorithmStore = defineStore('algorithm', {
  state: (): State => ({
    runs: [],
    assignments: null,
    events: [],
    loading: false,
    error: '',
  }),
  getters: {
    latestRun: (state) => state.runs[0] ?? null,
    activeRun: (state) => state.runs.find((run) => run.status === 'PENDING' || run.status === 'RUNNING') ?? null,
  },
  actions: {
    async refreshStatus(commandId?: string) {
      try {
        this.runs = await fetchAlgorithmStatus(commandId)
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法读取算法状态'
      }
    },
    async refreshAssignments(commandId?: string) {
      try {
        this.assignments = await fetchAlgorithmAssignments(commandId)
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法读取算法分配结果'
      }
    },
    async refreshEvents(commandId?: string) {
      try {
        this.events = await fetchAlgorithmEvents(commandId)
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法读取算法事件'
      }
    },
    async start(payload: AlgorithmStartPayload) {
      this.loading = true
      try {
        const run = await startAlgorithm(payload)
        this.runs = [run, ...this.runs.filter((item) => item.commandId !== run.commandId)]
        await Promise.all([this.refreshAssignments(run.commandId), this.refreshEvents(run.commandId)])
        this.error = ''
        return run
      } catch (error) {
        this.error = error instanceof Error ? error.message : '算法启动失败'
        throw error
      } finally {
        this.loading = false
      }
    },
    async stop(payload: AlgorithmStopPayload = {}) {
      this.loading = true
      try {
        const runs = await stopAlgorithm(payload)
        for (const run of runs) {
          this.runs = [run, ...this.runs.filter((item) => item.commandId !== run.commandId)]
        }
        this.error = ''
        return runs
      } catch (error) {
        this.error = error instanceof Error ? error.message : '算法停止失败'
        throw error
      } finally {
        this.loading = false
      }
    },
  },
})
