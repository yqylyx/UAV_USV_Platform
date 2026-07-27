export type VisualSensorStatus = 'ONLINE' | 'STALE' | 'WAITING'
export type VisualSensorDeviceType = 'UAV' | 'USV'
export type VisualSensorViewType = 'DOWN' | 'FORWARD'

export interface VisualSensor {
  cameraId: string
  deviceCode: string
  deviceType: VisualSensorDeviceType
  viewType: VisualSensorViewType
  displayName: string
  status: VisualSensorStatus
  source: string
  width: number
  height: number
  fps: number
  latencyMs: number
  timestampMs: number
  focused: boolean
}

export interface VisualSensorOverview {
  gatewayConnected: boolean
  gatewayDetail: string
  onlineCount: number
  totalCount: number
  focusedCameraId: string
  sensors: VisualSensor[]
}

export interface UnityVisualSensorFrame {
  cameraId: string
  deviceCode: string
  viewType: VisualSensorViewType
  source: string
  width: number
  height: number
  timestampMs: number
  sequence: number
  jpegBase64: string
}

export interface UnityVisualSensorMeta {
  width: number
  height: number
  fps: number
  timestampMs: number
  receivedAtMs: number
  sequence: number
  source: string
}
