import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RuntimeControlState } from '@/types/runtimeControl'

export type RuntimeCommandType =
  | 'START'
  | 'STOP'
  | 'TAKEOFF'
  | 'LAND'
  | 'START_MISSION'
  | 'STOP_MISSION'
  | 'SELECT_DEVICE'
  | 'FOCUS_DEVICE'
  | 'SWITCH_CAMERA'
  | 'TOGGLE_TRAJECTORY'

export interface RuntimeCommandPayload {
  commandType: RuntimeCommandType
  deviceCode?: string
  payload?: string
  detail?: string
}

export interface RuntimeCommandResult {
  commandType: RuntimeCommandType
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED'
  detail: string
  acceptedAt: string
}

export interface RuntimeCommandLog {
  id: number
  sessionId: number | null
  commandType: RuntimeCommandType
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED'
  requestedBy: string
  requestedAt: string
  completedAt: string | null
  detail: string
}

export async function fetchRuntimeControlStatus(): Promise<RuntimeControlState> {
  const response = await http.get<ApiResponse<RuntimeControlState>>('/runtime-control/status')
  return response.data.data
}

export async function fetchRuntimeCommandLogs(): Promise<RuntimeCommandLog[]> {
  const response = await http.get<ApiResponse<RuntimeCommandLog[]>>('/runtime-control/commands/recent')
  return response.data.data
}

export async function startRuntime(): Promise<RuntimeControlState> {
  await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/start', undefined, {
    timeout: 30000,
  })
  return response.data.data
}

export async function stopRuntime(): Promise<RuntimeControlState> {
  await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/stop', undefined, {
    timeout: 30000,
  })
  return response.data.data
}

export async function issueRuntimeCommand(payload: RuntimeCommandPayload): Promise<RuntimeCommandResult> {
  await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeCommandResult>>('/runtime-control/commands', payload)
  return response.data.data
}
