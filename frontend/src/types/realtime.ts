export type GatewayMessageType =
  | 'gateway.hello'
  | 'gateway.heartbeat'
  | 'telemetry.pose_batch'
  | 'mission.status'
  | 'control.command'
  | 'control.ack'
  | 'control.feedback'
  | 'control.result'

export interface GatewayEnvelope<TPayload = unknown> {
  version: string
  type: GatewayMessageType | string
  source: string
  timestamp: string
  runId?: string | null
  streamId: string
  frameId?: string | null
  sequence: number
  payload: TPayload
}

export interface RealtimeVector3 {
  x: number
  y: number
  z: number
}

export interface RealtimeQuaternion {
  x: number
  y: number
  z: number
  w: number
}

export interface RealtimeGeoPosition {
  latitudeDeg?: number
  longitudeDeg?: number
  altitudeMslM?: number
}

export interface VehiclePoseSample {
  deviceCode: string
  sourceTimestamp?: string
  sourceSequence?: number
  ageMs?: number
  fresh?: boolean
  positionValid?: boolean
  localPositionEnuM?: RealtimeVector3
  globalPosition?: RealtimeGeoPosition
  orientation?: RealtimeQuaternion
  linearVelocityMps?: RealtimeVector3
  headingDeg?: number
}

export interface PoseBatchPayload {
  snapshotMode?: string
  snapshotTime?: string
  complete?: boolean
  expectedDeviceCodes?: string[]
  missingDeviceCodes?: string[]
  staleDeviceCodes?: string[]
  vehicles: VehiclePoseSample[]
  freshnessThresholdMs?: number
}

export interface MissionStatusPayload {
  missionId?: string
  runId?: string
  state?: string
  phase?: string
  progress?: number
  activeCommandId?: string
  activeDeviceCodes?: string[]
}

export interface ControlEventPayload {
  commandId?: string
  status?: string
  code?: string
  message?: string
  retryable?: boolean
  progress?: number
  phase?: string
  activeDeviceCodes?: string[]
  startedAt?: string
  completedAt?: string
  metrics?: Record<string, unknown>
}
