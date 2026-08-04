import { defineStore } from 'pinia'

import { fetchRadarOverview } from '@/api/sensor'
import type { RadarOverview } from '@/types/sensor'

interface RadarSensorState {
  overview: RadarOverview | null
  loading: boolean
  error: string
}

export const useRadarSensorStore = defineStore('radar-sensor', {
  state: (): RadarSensorState => ({
    overview: null,
    loading: false,
    error: '',
  }),
  actions: {
    async refresh(silent = false) {
      if (!silent) this.loading = true
      this.error = ''
      try {
        this.overview = await fetchRadarOverview()
      } catch (error) {
        this.error = error instanceof Error ? error.message : '雷达数据加载失败'
      } finally {
        if (!silent) this.loading = false
      }
    },
  },
})
