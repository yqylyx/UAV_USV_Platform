export type DeviceType = 'UAV' | 'USV' | 'LIGHTHOUSE' | 'ROS_NODE' | 'UNITY_NODE'

export type DeviceStatus = 'ONLINE' | 'OFFLINE' | 'MAINTENANCE' | 'UNKNOWN'

export interface Device {
  id: number
  code: string
  name: string
  type: DeviceType
  status: DeviceStatus
  host: string | null
  port: number | null
  rosNamespace: string | null
  description: string | null
  createdAt: string
  updatedAt: string
}

export interface DeviceSavePayload {
  code: string
  name: string
  type: DeviceType
  status: DeviceStatus
  host: string
  port: number | null
  rosNamespace: string
  description: string
}

export interface DeviceQuery {
  keyword?: string
  type?: DeviceType
  status?: DeviceStatus
  page: number
  size: number
}
