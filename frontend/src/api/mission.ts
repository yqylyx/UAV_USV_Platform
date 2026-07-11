import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse, PageResponse } from '@/types/api'
import type { Mission, MissionDetail, MissionQuery, MissionSavePayload } from '@/types/mission'
import type { RuntimeCommandResult } from '@/api/runtimeControl'

export async function fetchMissions(query: MissionQuery): Promise<PageResponse<Mission>> {
  const response = await http.get<ApiResponse<PageResponse<Mission>>>('/missions', {
    params: query,
  })
  return response.data.data
}

export async function fetchMission(id: number): Promise<MissionDetail> {
  const response = await http.get<ApiResponse<MissionDetail>>(`/missions/${id}`)
  return response.data.data
}

export async function createMission(payload: MissionSavePayload): Promise<MissionDetail> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<MissionDetail>>('/missions', payload, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function updateMission(id: number, payload: MissionSavePayload): Promise<MissionDetail> {
  const csrf = await fetchCsrfToken()
  const response = await http.put<ApiResponse<MissionDetail>>(`/missions/${id}`, payload, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function deleteMission(id: number): Promise<void> {
  const csrf = await fetchCsrfToken()
  await http.delete<ApiResponse<null>>(`/missions/${id}`, {
    headers: { [csrf.headerName]: csrf.token },
  })
}

export type MissionAction = 'ready' | 'start' | 'pause' | 'resume' | 'complete' | 'fail' | 'cancel'

export interface MissionActionResult {
  detail: MissionDetail
  command: RuntimeCommandResult | null
}

export async function executeMissionAction(id: number, action: MissionAction): Promise<MissionActionResult> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<MissionActionResult>>(`/missions/${id}/${action}`, undefined, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}
