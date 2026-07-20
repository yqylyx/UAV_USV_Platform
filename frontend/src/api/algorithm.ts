import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'

export type AlgorithmType = 'CAPTURE' | 'ESCORT_DEFENSE'
export type AlgorithmRunStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TIMEOUT' | 'STOPPED'
export type AlgorithmEventLevel = 'INFO' | 'WARN' | 'ERROR'
export type AlgorithmAssignmentRole = 'TRACK' | 'INTERCEPT' | 'ENCIRCLE' | 'ESCORT' | 'DEFEND' | 'RETURN' | 'STANDBY'

export interface AlgorithmStartPayload {
  algorithmType: AlgorithmType
  targetId?: string
  uavIds?: string[]
  usvIds?: string[]
  parameters?: Record<string, unknown>
}

export interface AlgorithmStopPayload {
  commandId?: string
  reason?: string
}

export interface AlgorithmRun {
  commandId: string
  algorithmType: AlgorithmType
  status: AlgorithmRunStatus
  targetId: string | null
  stage: string | null
  message: string | null
  startedAt: string
  lastAckAt: string | null
  completedAt: string | null
  updatedAt: string
  errorMessage: string | null
}

export interface AlgorithmAssignmentItem {
  vehicleId: string
  vehicleCode: string | null
  role: AlgorithmAssignmentRole
  x: number | null
  y: number | null
  z: number | null
  heading: number | null
  detail: string | null
}

export interface AlgorithmAssignments {
  commandId: string
  targetId: string | null
  assignments: AlgorithmAssignmentItem[]
}

export interface AlgorithmEvent {
  commandId: string | null
  algorithmType: AlgorithmType | null
  level: AlgorithmEventLevel
  stage: string | null
  message: string
  occurredAt: string
}

export async function startAlgorithm(payload: AlgorithmStartPayload): Promise<AlgorithmRun> {
  await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRun>>('/algorithm/start', payload)
  return response.data.data
}

export async function stopAlgorithm(payload: AlgorithmStopPayload = {}): Promise<AlgorithmRun[]> {
  await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRun[]>>('/algorithm/stop', payload)
  return response.data.data
}

export async function fetchAlgorithmStatus(commandId?: string): Promise<AlgorithmRun[]> {
  const response = await http.get<ApiResponse<AlgorithmRun[]>>('/algorithm/status', {
    params: commandId ? { commandId } : undefined,
  })
  return response.data.data
}

export async function fetchAlgorithmAssignments(commandId?: string): Promise<AlgorithmAssignments> {
  const response = await http.get<ApiResponse<AlgorithmAssignments>>('/algorithm/assignments', {
    params: commandId ? { commandId } : undefined,
  })
  return response.data.data
}

export async function fetchAlgorithmEvents(commandId?: string): Promise<AlgorithmEvent[]> {
  const response = await http.get<ApiResponse<AlgorithmEvent[]>>('/algorithm/events', {
    params: commandId ? { commandId } : undefined,
  })
  return response.data.data
}
