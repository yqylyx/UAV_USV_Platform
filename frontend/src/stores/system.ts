import { defineStore } from 'pinia'

import { fetchPlatformComponents, fetchSystemHealth } from '@/api/system'
import type { PlatformComponent, SystemHealth } from '@/types/system'

interface SystemState {
  health: SystemHealth | null
  components: PlatformComponent[]
  loading: boolean
  error: string
}

export const useSystemStore = defineStore('system', {
  state: (): SystemState => ({
    health: null,
    components: [],
    loading: false,
    error: '',
  }),
  actions: {
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        const [health, components] = await Promise.all([
          fetchSystemHealth(),
          fetchPlatformComponents(),
        ])
        this.health = health
        this.components = components
      } catch (error) {
        this.health = null
        this.components = []
        this.error = error instanceof Error ? error.message : '无法连接后端服务'
      } finally {
        this.loading = false
      }
    },
  },
})

