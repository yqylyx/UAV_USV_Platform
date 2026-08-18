import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { RadarOverview } from '@/types/sensor'

export async function fetchRadarOverview(): Promise<RadarOverview> {
  const response = await http.get<ApiResponse<RadarOverview>>('/sensors/radar')
  return response.data.data
}
