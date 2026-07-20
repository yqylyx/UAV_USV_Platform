import { http } from './http'

import type { ApiResponse } from '@/types/api'
import type {
  AlgorithmCommandResult,
  AlgorithmEvent,
  AlgorithmMissionSnapshot,
  AlgorithmMissionSummary,
  AlgorithmResetRequest,
  AlgorithmStartRequest,
  AlgorithmStopRequest,
  AlgorithmAssignment,
  AlgorithmTacticalScene,
} from '@/types/algorithmMission'

export async function startAlgorithmMission(
  payload: AlgorithmStartRequest,
) {
  const response = await http.post<ApiResponse<AlgorithmCommandResult>>(
    '/algorithm/start',
    payload,
  )

  return response.data.data
}

export async function stopAlgorithmMission(
  payload: AlgorithmStopRequest,
) {
  const response = await http.post<ApiResponse<AlgorithmCommandResult>>(
    '/algorithm/stop',
    payload,
  )

  return response.data.data
}

export async function resetAlgorithmMission(
  payload: AlgorithmResetRequest,
) {
  const response = await http.post<ApiResponse<AlgorithmCommandResult>>(
    '/algorithm/reset',
    payload,
  )

  return response.data.data
}

export async function fetchAlgorithmMissionStatus(runId: string) {
  const response = await http.get<ApiResponse<AlgorithmMissionSummary>>(
    '/algorithm/status',
    {
      params: { runId },
    },
  )

  return response.data.data
}

export async function fetchAlgorithmAssignments(runId: string) {
  const response = await http.get<ApiResponse<AlgorithmAssignment[]>>(
    '/algorithm/assignments',
    {
      params: { runId },
    },
  )

  return response.data.data
}

export async function fetchAlgorithmEvents(runId: string) {
  const response = await http.get<ApiResponse<AlgorithmEvent[]>>(
    '/algorithm/events',
    {
      params: { runId },
    },
  )

  return response.data.data
}

export async function fetchAlgorithmTacticalScene(runId: string) {
  const response = await http.get<ApiResponse<AlgorithmTacticalScene>>(
    '/algorithm/tactical-scene',
    {
      params: { runId },
    },
  )

  return response.data.data
}

export async function fetchAlgorithmMissionSnapshot(
  runId: string,
): Promise<AlgorithmMissionSnapshot> {
  const [
    summary,
    assignments,
    events,
    scene,
  ] = await Promise.all([
    fetchAlgorithmMissionStatus(runId),
    fetchAlgorithmAssignments(runId),
    fetchAlgorithmEvents(runId),
    fetchAlgorithmTacticalScene(runId),
  ])

  return {
    summary,
    assignments,
    events,
    scene,
    refreshedAt: new Date().toISOString(),
  }
}