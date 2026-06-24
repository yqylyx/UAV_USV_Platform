import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RuntimeNode, RuntimeNodeQuery, RuntimeSummary } from '@/types/monitoring'

export async function fetchRuntimeSummary(): Promise<RuntimeSummary> {
  const response = await http.get<ApiResponse<RuntimeSummary>>('/monitoring/summary')
  return response.data.data
}

export async function fetchRuntimeNodes(query: RuntimeNodeQuery = {}): Promise<RuntimeNode[]> {
  const response = await http.get<ApiResponse<RuntimeNode[]>>('/monitoring/nodes', {
    params: query,
  })
  return response.data.data
}
