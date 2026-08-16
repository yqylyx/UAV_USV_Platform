import type { DeviceStatus, DeviceType } from './device'

export interface RuntimeNode {
  id: number
  code: string
  name: string
  type: DeviceType
  status: DeviceStatus
  host: string | null
  port: number | null
  endpoint: string
  rosNamespace: string | null
  lastHeartbeatAt: string | null
  heartbeatAgeSeconds: number
  source: string
  instanceId: string | null
  positionX: number | null
  positionY: number | null
  positionZ: number | null
  latitude?: number | null
  longitude?: number | null
  batteryLevel?: number | null
  linkQualityPercent?: number | null
  telemetryAt?: string | null
  telemetrySource?: string | null
  telemetryStale?: boolean
  controlOperationalState?: string
  controlStateFresh?: boolean
  controlStateReceivedAt?: string | null
  controlConnectionState?: string
  detail: string | null
}

export interface RuntimeSummary {
  totalNodes: number
  onlineNodes: number
  offlineNodes: number
  warningNodes: number
  unknownNodes: number
  rosNodes: number
  unityNodes: number
  vehicleNodes: number
  refreshedAt: string
}

export interface RuntimeNodeQuery {
  type?: DeviceType
  status?: DeviceStatus
}
