import { defineStore } from 'pinia'

import { fetchDevices } from '@/api/device'
import type { Device, DeviceQuery, DeviceStatus, DeviceType } from '@/types/device'

interface DeviceState {
  records: Device[]
  total: number
  page: number
  size: number
  totalPages: number
  keyword: string
  type?: DeviceType
  status?: DeviceStatus
  loading: boolean
  error: string
}

export const useDeviceStore = defineStore('device', {
  state: (): DeviceState => ({
    records: [],
    total: 0,
    page: 0,
    size: 10,
    totalPages: 0,
    keyword: '',
    type: undefined,
    status: undefined,
    loading: false,
    error: '',
  }),
  actions: {
    async refresh(overrides: Partial<DeviceQuery> = {}) {
      const query: DeviceQuery = {
        keyword: overrides.keyword ?? (this.keyword || undefined),
        type: overrides.type ?? this.type,
        status: overrides.status ?? this.status,
        page: overrides.page ?? this.page,
        size: overrides.size ?? this.size,
      }

      this.loading = true
      this.error = ''
      try {
        const result = await fetchDevices(query)
        this.records = result.records
        this.total = result.total
        this.page = result.page
        this.size = result.size
        this.totalPages = result.totalPages
      } catch (error) {
        this.records = []
        this.total = 0
        this.error = error instanceof Error ? error.message : '设备数据加载失败'
      } finally {
        this.loading = false
      }
    },
  },
})
