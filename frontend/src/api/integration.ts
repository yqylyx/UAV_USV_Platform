import { http } from './http'
import type { ApiResponse } from '@/types/api'

export type IntegrationState = 'ONLINE' | 'RUNNING' | 'STOPPED' | 'OFFLINE' | 'FAILED'

export interface IntegrationHeartbeatPayload {
  componentCode: 'unity-client-01'
  instanceId: string
  state: IntegrationState
  detail: string
  rosConnectionStatus: string
}

const integrationToken = import.meta.env.VITE_PLATFORM_INTEGRATION_TOKEN ?? 'uav-usv-local-agent'

export async function sendIntegrationHeartbeat(payload: IntegrationHeartbeatPayload): Promise<void> {
  await http.post<ApiResponse<{ accepted: boolean }>>('/integration/heartbeat', payload, {
    headers: {
      'X-Platform-Token': integrationToken,
    },
  })
}