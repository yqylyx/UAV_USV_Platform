import { fetchCsrfToken } from './auth'
import { http } from './http'
import type { ApiResponse, PageResponse } from '@/types/api'
import type { Device, DeviceQuery, DeviceSavePayload } from '@/types/device'

export async function fetchDevices(query: DeviceQuery): Promise<PageResponse<Device>> {
  const response = await http.get<ApiResponse<PageResponse<Device>>>('/devices', {
    params: query,
  })
  return response.data.data
}

export async function createDevice(payload: DeviceSavePayload): Promise<Device> {
  const csrf = await fetchCsrfToken()
  const response = await http.post<ApiResponse<Device>>('/devices', payload, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function updateDevice(id: number, payload: DeviceSavePayload): Promise<Device> {
  const csrf = await fetchCsrfToken()
  const response = await http.put<ApiResponse<Device>>(`/devices/${id}`, payload, {
    headers: { [csrf.headerName]: csrf.token },
  })
  return response.data.data
}

export async function deleteDevice(id: number): Promise<void> {
  const csrf = await fetchCsrfToken()
  await http.delete<ApiResponse<null>>(`/devices/${id}`, {
    headers: { [csrf.headerName]: csrf.token },
  })
}
