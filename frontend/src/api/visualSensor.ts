import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { VisualSensorOverview } from '@/types/visualSensor'

export async function fetchVisualSensors(): Promise<VisualSensorOverview> {
  const response = await http.get<ApiResponse<VisualSensorOverview>>('/visual-sensors')
  return response.data.data
}

export async function focusVisualSensor(cameraId: string): Promise<VisualSensorOverview> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<VisualSensorOverview>>(
    `/visual-sensors/${encodeURIComponent(cameraId)}/focus`,
    undefined,
    { headers: { [csrf.headerName]: csrf.token } },
  )
  return response.data.data
}

export async function fetchVisualSensorFrame(cameraId: string): Promise<Blob | null> {
  const response = await http.get<Blob>(
    `/visual-sensors/${encodeURIComponent(cameraId)}/frame`,
    {
      responseType: 'blob',
      timeout: 3500,
      headers: { Accept: 'image/jpeg' },
      validateStatus: (status) => status === 200 || status === 204,
    },
  )
  return response.status === 200 && response.data.size > 0 ? response.data : null
}
