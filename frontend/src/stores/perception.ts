import { defineStore } from 'pinia'

import {
  fetchPerceptionSensors,
  fetchPerceptionTargets,
  type PerceptionSensor,
  type PerceptionTarget,
} from '@/api/perception'

interface State {
  sensors: PerceptionSensor[]
  targets: PerceptionTarget[]
  loading: boolean
  error: string
}

export const usePerceptionStore = defineStore('perception', {
  state: (): State => ({
    sensors: [],
    targets: [],
    loading: false,
    error: '',
  }),
  getters: {
    onlineSensorCount: (state) => state.sensors.filter((sensor) => sensor.online && sensor.healthy).length,
    hostileTargetCount: (state) => state.targets.filter((target) => target.affiliation === 'HOSTILE').length,
  },
  actions: {
    async refresh() {
      this.loading = true
      try {
        const [sensors, targets] = await Promise.all([fetchPerceptionSensors(), fetchPerceptionTargets()])
        this.sensors = sensors
        this.targets = targets
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法读取感知模拟数据'
      } finally {
        this.loading = false
      }
    },
  },
})
