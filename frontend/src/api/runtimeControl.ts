import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RuntimeControlState } from '@/types/runtimeControl'

export async function fetchRuntimeControlStatus(): Promise<RuntimeControlState> {
  const response = await http.get<ApiResponse<RuntimeControlState>>('/runtime-control/status')
  return response.data.data
}

export async function startRuntime(): Promise<RuntimeControlState> {
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/start', undefined, { timeout: 30000 })
  return response.data.data
}

export async function stopRuntime(): Promise<RuntimeControlState> {
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/stop', undefined, { timeout: 30000 })
  return response.data.data
}
