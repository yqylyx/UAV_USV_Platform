import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RuntimeControlState } from '@/types/runtimeControl'

export type RuntimeCommandType =
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

export async function fetchRuntimeControlStatus(): Promise<RuntimeControlState> {
  const response = await http.get<ApiResponse<RuntimeControlState>>('/runtime-control/status')
  return response.data.data
}

export async function startRuntime(): Promise<RuntimeControlState> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/start', undefined, {
    headers: { [csrf.headerName]: csrf.token },
    timeout: 30000,
  })
  return response.data.data
}

export async function stopRuntime(): Promise<RuntimeControlState> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeControlState>>('/runtime-control/stop', undefined, {
    headers: { [csrf.headerName]: csrf.token },
    timeout: 30000,
  })
  return response.data.data
}

export async function issueRuntimeCommand(payload: RuntimeCommandPayload): Promise<RuntimeCommandResult> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<RuntimeCommandResult>>('/runtime-control/commands', payload, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}
