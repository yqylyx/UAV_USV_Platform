import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { PlatformComponent, SystemHealth } from '@/types/system'

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const response = await http.get<ApiResponse<SystemHealth>>('/system/health')
  return response.data.data
}

export async function fetchPlatformComponents(): Promise<PlatformComponent[]> {
  const response = await http.get<ApiResponse<PlatformComponent[]>>('/system/components')
  return response.data.data
}
