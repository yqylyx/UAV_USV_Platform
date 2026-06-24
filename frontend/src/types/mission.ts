import type { DeviceStatus, DeviceType } from './device'

export type MissionType =
  | 'TARGET_INSPECTION'
  | 'COOPERATIVE_ENCIRCLEMENT'
  | 'PATH_TRACKING'
  | 'COMMUNICATION_RELAY'
  | 'CUSTOM'

export type MissionStatus =
  | 'DRAFT'
  | 'READY'
  | 'RUNNING'
  | 'PAUSED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type MissionStage =
  | 'PREPARE'
  | 'TARGET_DETECTED'
  | 'ASSIGNMENT'
  | 'TRACKING'
  | 'ENCIRCLEMENT'
  | 'CAPTURED'
  | 'EVALUATION'

export type MissionDeviceRole =
  | 'LEADER'
  | 'UAV_RECON'
  | 'UAV_TRACK'
  | 'USV_INTERCEPT'
  | 'USV_BLOCKADE'
  | 'ROS_BRIDGE'
  | 'UNITY_CLIENT'

export type MissionEventType = 'CONFIG' | 'STATUS' | 'DEVICE' | 'ROS' | 'UNITY' | 'ALERT' | 'NOTE'

export interface Mission {
  id: number
  code: string
  name: string
  type: MissionType
  status: MissionStatus
  stage: MissionStage
  priority: number
  targetName: string | null
  targetBehavior: string | null
  missionArea: string | null
  plannedStartAt: string | null
  plannedEndAt: string | null
  description: string | null
  deviceCount: number
  createdAt: string
  updatedAt: string
}

export interface MissionDeviceBinding {
  id: number
  deviceId: number
  code: string | null
  name: string | null
  type: DeviceType | null
  status: DeviceStatus | null
  role: MissionDeviceRole
  callSign: string | null
  required: boolean
  assignedAt: string
  notes: string | null
}

export interface MissionParameter {
  id: number
  key: string
  value: string | null
  unit: string | null
  description: string | null
}

export interface MissionEvent {
  id: number
  eventType: MissionEventType
  title: string
  message: string | null
  source: string | null
  occurredAt: string
}

export interface MissionDetail {
  mission: Mission
  devices: MissionDeviceBinding[]
  parameters: MissionParameter[]
  events: MissionEvent[]
}

export interface MissionDeviceBindingPayload {
  deviceId: number
  role: MissionDeviceRole
  callSign: string
  required: boolean
  notes: string
}

export interface MissionParameterPayload {
  key: string
  value: string
  unit: string
  description: string
}

export interface MissionSavePayload {
  code: string
  name: string
  type: MissionType
  status: MissionStatus
  stage: MissionStage
  priority: number
  targetName: string
  targetBehavior: string
  missionArea: string
  plannedStartAt: string | null
  plannedEndAt: string | null
  description: string
  devices: MissionDeviceBindingPayload[]
  parameters: MissionParameterPayload[]
}

export interface MissionQuery {
  keyword?: string
  type?: MissionType
  status?: MissionStatus
  page: number
  size: number
}
