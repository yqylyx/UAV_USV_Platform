import { defineStore } from 'pinia'

import { fetchRuntimeControlStatus, startRuntime, stopRuntime } from '@/api/runtimeControl'
import type { RuntimeControlState } from '@/types/runtimeControl'

interface State {
  runtime: RuntimeControlState | null
  loading: boolean
  error: string
}

export const useRuntimeControlStore = defineStore('runtimeControl', {
  state: (): State => ({ runtime: null, loading: false, error: '' }),
  actions: {
    async refresh() {
      try {
        this.runtime = await fetchRuntimeControlStatus()
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法读取运行控制状态'
      }
    },
    async start() {
      this.loading = true
      try {
        this.runtime = await startRuntime()
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '启动失败'
      } finally {
        this.loading = false
      }
    },
    async stop() {
      this.loading = true
      try {
        this.runtime = await stopRuntime()
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '停止失败'
      } finally {
        this.loading = false
      }
    },
  },
})
