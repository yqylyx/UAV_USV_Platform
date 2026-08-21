import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { AlgorithmDefinition, AlgorithmRuntimeFrame, AlgorithmRuntimeStatus } from '@/types/mission'

export async function fetchAlgorithms(): Promise<AlgorithmDefinition[]> {
  const response = await http.get<ApiResponse<AlgorithmDefinition[]>>('/algorithms')
  return response.data.data
}

export async function setAlgorithmEnabled(code: string, enabled: boolean): Promise<AlgorithmDefinition> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmDefinition>>(`/algorithms/${code}/enabled`, undefined, {
    params: { enabled }, headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function setDefaultAlgorithm(code: string): Promise<AlgorithmDefinition> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmDefinition>>(`/algorithms/${code}/default`, undefined, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function prepareAlgorithmRun(runId: number, algorithmCode: string, config: Record<string, unknown>): Promise<AlgorithmRuntimeStatus> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRuntimeStatus>>(`/algorithm-runs/${runId}/prepare`, { algorithmCode, config }, {
    headers: { [csrf.headerName]: csrf.token }, timeout: 20000,
  })
  return response.data.data
}

export async function controlAlgorithmRun(runId: number, action: 'start' | 'pause' | 'resume' | 'cancel' | 'stop'): Promise<AlgorithmRuntimeStatus> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRuntimeStatus>>(`/algorithm-runs/${runId}/${action}`, undefined, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function fetchAlgorithmFrame(runId: number, afterSequence = 0): Promise<AlgorithmRuntimeFrame | null> {
  const response = await http.get<ApiResponse<AlgorithmRuntimeFrame | null>>(`/algorithm-runs/${runId}/frame`, {
    params: { afterSequence }, timeout: 4000,
  })
  return response.data.data
}

export async function fetchAlgorithmFrames(runId: number, afterSequence = 0, signal?: AbortSignal): Promise<AlgorithmRuntimeFrame[]> {
  const response = await http.get<ApiResponse<AlgorithmRuntimeFrame[]>>(`/algorithm-runs/${runId}/frames`, {
    params: { afterSequence }, timeout: 4000, signal,
  })
  return response.data.data ?? []
}

export async function placeEscortThreat(runId: number, x: number, y: number): Promise<AlgorithmRuntimeStatus> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRuntimeStatus>>(`/algorithm-runs/${runId}/threat`, { x, y }, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function activateEscortCapture(runId: number, threatCode?: string): Promise<AlgorithmRuntimeStatus> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<AlgorithmRuntimeStatus>>(`/algorithm-runs/${runId}/active-capture`, undefined, {
    params: threatCode ? { threatCode } : undefined,
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}
