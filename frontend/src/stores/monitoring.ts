import { defineStore } from 'pinia'

import { fetchRuntimeNodes, fetchRuntimeSummary } from '@/api/monitoring'
import type { DeviceStatus, DeviceType } from '@/types/device'
import type { RuntimeNode, RuntimeNodeQuery, RuntimeSummary } from '@/types/monitoring'

let runtimeEvents: EventSource | null = null
let refreshTimer: number | null = null

interface MonitoringState {
  summary: RuntimeSummary | null
  nodes: RuntimeNode[]
  type?: DeviceType
  status?: DeviceStatus
  loading: boolean
  error: string
}

export const useMonitoringStore = defineStore('monitoring', {
  state: (): MonitoringState => ({
    summary: null,
    nodes: [],
    type: undefined,
    status: undefined,
    loading: false,
    error: '',
  }),
  actions: {
    async refresh(overrides: RuntimeNodeQuery = {}, silent = false) {
      const query: RuntimeNodeQuery = {
        type: overrides.type ?? this.type,
        status: overrides.status ?? this.status,
      }

      if (!silent) this.loading = true
      this.error = ''
      try {
        const [summary, nodes] = await Promise.all([fetchRuntimeSummary(), fetchRuntimeNodes(query)])
        this.summary = summary
        this.nodes = nodes
      } catch (error) {
        this.nodes = []
        this.error = error instanceof Error ? error.message : '运行监控数据加载失败'
      } finally {
        if (!silent) this.loading = false
      }
    },
    connectEvents() {
      if (runtimeEvents) return
      runtimeEvents = new EventSource('/api/monitoring/events')
      runtimeEvents.addEventListener('runtime-change', () => {
        if (refreshTimer !== null) window.clearTimeout(refreshTimer)
        refreshTimer = window.setTimeout(() => this.refresh({}, true), 1000)
      })
      runtimeEvents.onerror = () => {
        this.error = '实时状态连接中断，正在自动重连'
      }
      runtimeEvents.onopen = () => {
        if (this.error === '实时状态连接中断，正在自动重连') this.error = ''
      }
    },
    disconnectEvents() {
      runtimeEvents?.close()
      runtimeEvents = null
      if (refreshTimer !== null) window.clearTimeout(refreshTimer)
      refreshTimer = null
    },
  },
})
