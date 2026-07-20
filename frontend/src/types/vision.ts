export type VisionSensorType = 'CAMERA' | 'LIDAR'

export type VisionAffiliation =
  | 'FRIENDLY'
  | 'HOSTILE'
  | 'NEUTRAL'
  | 'UNKNOWN'

export interface VisionSensorStatus {
  vehicleId: string
  sensorId: string
  sensorType: VisionSensorType
  online: boolean | null
  healthy: boolean | null
  measuredRateHz: number | null
  latencyMs: number | null
  tfAvailable: boolean | null
  lastUpdateTime: string | null
}

export interface VisionDetection {
  trackId: string
  className: string
  sensorSource: string
  sourceLabel: string
  affiliation: VisionAffiliation
  classConfidence: number
  x: number
  y: number
  speedX: number
  speedY: number
  lastUpdateTime: string
}

export interface VisionCameraSource {
  vehicleId: string
  sensorId: string
  displayName: string
  topic: string
  online: boolean
  streamUrl: string | null
}