import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { GatewayPoseBatch, GatewayRuntimeSnapshot, RuntimeNode, RuntimeNodeQuery, RuntimeSummary } from '@/types/monitoring'

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

export async function fetchLatestPoseBatch(): Promise<Omit<GatewayPoseBatch, 'receivedAt'> | null> {
  const response = await http.get<ApiResponse<Omit<GatewayPoseBatch, 'receivedAt'> | null>>('/monitoring/pose-batch/latest')
  return response.data.data
}

export async function fetchLatestGatewayState(): Promise<GatewayRuntimeSnapshot> {
  const response = await http.get<ApiResponse<GatewayRuntimeSnapshot>>('/monitoring/gateway/latest')
  return response.data.data
}
