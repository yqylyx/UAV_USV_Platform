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

export interface GatewayVehiclePose {
  deviceCode: string
  sourceSequence: number
  sourceTimestampMs: number
  ageMs: number
  fresh: boolean
  x: number
  y: number
  z: number
  localX: number
  localY: number
  localZ: number
  qx: number
  qy: number
  qz: number
  qw: number
  headingDeg: number
}

export interface GatewayPoseBatch {
  sequence: number
  timestampMs: number
  source: string
  missionId: string
  runId: string
  complete: boolean
  coordinateFrame: {
    originX: number
    originY: number
    originZ: number
    source: string
  }
  vehicles: GatewayVehiclePose[]
  receivedAt: number
}

export interface GatewayMissionStatus {
  missionId: string
  runId: string
  state: string
  phase: string
  progress: number
  activeCommandId: string
  activeDeviceCodes: string[]
  sequence: number
  timestampMs: number
}

export interface GatewayDeviceStatus {
  deviceCode: string
  connectionState: string
  operationState: string
  controlMode: string
  armed: boolean
  batteryPercent: number
  signalRssiDbm: number
  speedMps: number
  headingDeg: number
  gpsFixType: number
  satelliteCount: number
  health: string
  activeCommandId: string
  sequence: number
  timestampMs: number
}

export interface GatewayDetectionStatus {
  messageType: string
  sensorId: string
  frameSequence: number
  sourceTimestampMs: number
  detectionCount: number
  sequence: number
  targets: GatewaySceneTarget[]
}

export interface GatewaySceneTarget {
  trackId: string
  type: 'CAPTURE_TARGET' | 'ESCORT_TARGET'
  confidence: number
  x: number
  y: number
  z: number
  localX: number
  localY: number
  localZ: number
}

export interface GatewayRuntimeSnapshot {
  mission: GatewayMissionStatus | null
  devices: GatewayDeviceStatus[]
  perception: Record<string, GatewayDetectionStatus>
  latestError: { code: string; message: string; retryable: boolean; details: Record<string, string>; timestampMs: number } | null
  updatedAt: number
}
