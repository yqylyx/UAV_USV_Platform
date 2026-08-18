import type { DeviceStatus, DeviceType } from './device'

export type MissionType =
  | 'TARGET_INSPECTION'
  | 'COOPERATIVE_ENCIRCLEMENT'
  | 'COOPERATIVE_ESCORT'
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

export type MissionExecutionMode = 'ROS_GAZEBO' | 'UNITY_STANDALONE' | 'HYBRID_MIRROR'

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
export type MissionRunStatus = 'PENDING' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
export type MissionEventLevel = 'INFO' | 'WARNING' | 'ERROR'

export interface Mission {
  id: number
  code: string
  name: string
  type: MissionType
  executionMode: MissionExecutionMode
  algorithmCode: string
  algorithmVersion: string
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
  runId: number | null
  eventType: MissionEventType
  stage: MissionStage | null
  level: MissionEventLevel
  title: string
  message: string | null
  source: string | null
  occurredAt: string
}

export interface MissionRun {
  id: number
  sessionId: number | null
  runKey: string
  runNo: number
  status: MissionRunStatus
  stage: MissionStage
  requestedBy: string | null
  startedAt: string
  pausedAt: string | null
  endedAt: string | null
  failureReason: string | null
  runtimeInstanceId: string | null
  algorithmCode: string | null
  algorithmVersion: string | null
}

export interface MissionDetail {
  mission: Mission
  devices: MissionDeviceBinding[]
  parameters: MissionParameter[]
  events: MissionEvent[]
  currentRun: MissionRun | null
  runs: MissionRun[]
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
  executionMode: MissionExecutionMode
  algorithmCode: string
  algorithmVersion: string
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
  executionMode?: MissionExecutionMode
  page: number
  size: number
}

export interface MissionSummary {
  total: number
  ready: number
  running: number
  abnormal: number
}

export interface AlgorithmDefinition {
  id: number
  code: string
  name: string
  version: string
  missionType: MissionType
  adapterType: 'PYTHON_PROCESS' | 'UNITY_NATIVE' | string
  deviceScale: string
  enabled: boolean
  defaultForType: boolean
  description: string
}

export interface AlgorithmAgentFrame {
  code: string
  type: 'UAV' | 'USV'
  x: number
  y: number
  z: number
  heading: number
  role: string
  status: string
}

export interface AlgorithmTargetFrame {
  code: string
  type: 'CAPTURE_TARGET' | 'ESCORT_TARGET' | 'THREAT_TARGET'
  x: number
  y: number
  z: number
  heading: number
  visible: boolean
}

export interface AlgorithmRuntimeFrame {
  runId: number
  algorithmCode: string
  coordinateFrame?: 'FLEET_LOCAL_ENU' | 'GLOBAL_ENU'
  sequence: number
  timestamp: number
  phase: string
  agents: AlgorithmAgentFrame[]
  targets: AlgorithmTargetFrame[]
  metrics: Record<string, unknown>
  route: number[][]
  obstacles: Array<Record<string, unknown>>
  terminalStatus: string | null
}

export interface AlgorithmRuntimeStatus {
  runId: number
  algorithmCode: string
  state: string
  latestSequence: number
  error: string | null
  latestFrame: AlgorithmRuntimeFrame | null
}

export interface MissionPreflightIssue {
  code: string
  level: 'ERROR' | 'WARNING'
  message: string
}

export interface MissionPreflight {
  missionId: number
  missionStatus: MissionStatus
  executionMode: MissionExecutionMode
  configurationComplete: boolean
  requiredDeviceCount: number
  onlineRequiredDeviceCount: number
  offlineDeviceCodes: string[]
  rosOnline: boolean
  unityOnline: boolean
  unityControlsReady: boolean
  unityRecognizedDeviceCount: number
  unityTrajectorySequence: number | null
  hasOpenRun: boolean
  canStart: boolean
  issues: MissionPreflightIssue[]
  checkedAt: string
}
