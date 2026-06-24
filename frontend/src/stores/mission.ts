import { defineStore } from 'pinia'

import { fetchMissions } from '@/api/mission'
import type { Mission, MissionQuery, MissionStatus, MissionType } from '@/types/mission'

interface MissionState {
  records: Mission[]
  total: number
  page: number
  size: number
  totalPages: number
  keyword: string
  type?: MissionType
  status?: MissionStatus
  loading: boolean
  error: string
}

export const useMissionStore = defineStore('mission', {
  state: (): MissionState => ({
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
    async refresh(overrides: Partial<MissionQuery> = {}) {
      const query: MissionQuery = {
        keyword: overrides.keyword ?? (this.keyword || undefined),
        type: overrides.type ?? this.type,
        status: overrides.status ?? this.status,
        page: overrides.page ?? this.page,
        size: overrides.size ?? this.size,
      }

      this.loading = true
      this.error = ''
      try {
        const result = await fetchMissions(query)
        this.records = result.records
        this.total = result.total
        this.page = result.page
        this.size = result.size
        this.totalPages = result.totalPages
      } catch (error) {
        this.records = []
        this.total = 0
        this.error = error instanceof Error ? error.message : '任务数据加载失败'
      } finally {
        this.loading = false
      }
    },
  },
})
