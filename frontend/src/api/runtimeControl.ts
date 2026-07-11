import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RuntimeControlState } from '@/types/runtimeControl'

export type RuntimeCommandType =
  | 'START'
  | 'STOP'
  | 'TAKEOFF'
  | 'LAND'
  | 'UAV_TAKEOFF'
  | 'UAV_HOVER'
  | 'UAV_RESUME'
  | 'UAV_RETURN'
  | 'UAV_LAND'
  | 'UAV_EMERGENCY_LAND'
  | 'USV_DEPART'
  | 'USV_HOLD'
  | 'USV_RESUME'
  | 'USV_RETURN'
  | 'USV_STOP'
  | 'USV_EMERGENCY_STOP'
  | 'START_MISSION'
  | 'STOP_MISSION'
  | 'PAUSE_MISSION'
  | 'RESUME_MISSION'
  | 'COMPLETE_MISSION'
  | 'FAIL_MISSION'
  | 'CANCEL_MISSION'
  | 'SELECT_DEVICE'
  | 'FOCUS_DEVICE'
  | 'SWITCH_CAMERA'
  | 'TOGGLE_TRAJECTORY'

export interface RuntimeCommandPayload {
  commandType: RuntimeCommandType
  runId?: number
  deviceCode?: string
  payload?: string
  detail?: string
}

export interface RuntimeCommandResult {
  id: number
  commandKey: string
  commandType: RuntimeCommandType
  status: RuntimeCommandStatus
  detail: string
  acceptedAt: string
}

export interface RuntimeCommandLog {
  id: number
  sessionId: number | null
  runId: number | null
  deviceId: number | null
  commandKey: string
  commandType: RuntimeCommandType
  status: RuntimeCommandStatus
  requestedBy: string
  requestedAt: string
  dispatchedAt: string | null
  acknowledgedAt: string | null
  completedAt: string | null
  detail: string
  errorCode: string | null
}

export type RuntimeCommandStatus = 'PENDING' | 'DISPATCHED' | 'ACKNOWLEDGED' | 'FAILED' | 'TIMEOUT'

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
