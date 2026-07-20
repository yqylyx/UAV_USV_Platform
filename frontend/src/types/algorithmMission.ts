export type AlgorithmMissionType = 'CAPTURE' | 'ESCORT_DEFENSE'

export type AlgorithmMissionStatus =
  | 'IDLE'
  | 'SEARCHING'
  | 'TRACKING'
  | 'APPROACHING'
  | 'ENCIRCLING'
  | 'HOLDING'
  | 'ESCORTING'
  | 'THREAT_DETECTED'
  | 'REORGANIZING'
  | 'INTERCEPTING'
  | 'SUCCESS'
  | 'FAILED'

export type AlgorithmVehicleType = 'UAV' | 'USV'

export interface AlgorithmMissionSummary {
  missionType: AlgorithmMissionType
  algorithmName: string
  status: AlgorithmMissionStatus
  statusName: string
  targetId: string
  participatingUavs: number
  participatingUsvs: number
  progress: number
  elapsedSeconds: number
  degraded: boolean
  detail: string
}

export interface AlgorithmAssignment {
  vehicleId: string
  vehicleType: AlgorithmVehicleType
  roleName: string
  targetId: string
  targetX: number
  targetY: number
  assignmentCost: number
  active: boolean
  status: string
}

export interface AlgorithmEvent {
  id: string
  time: string
  level: 'INFO' | 'WARNING' | 'SUCCESS' | 'ERROR'
  stage: string
  message: string
}

export interface AlgorithmTacticalScene {
  centerLabel: string
  centerX: number
  centerY: number
  threatLabel: string | null
  threatX: number | null
  threatY: number | null
}

export interface AlgorithmMissionPreview {
  summary: AlgorithmMissionSummary
  scene: AlgorithmTacticalScene
  assignments: AlgorithmAssignment[]
  events: AlgorithmEvent[]
}

export interface CaptureAlgorithmStartRequest {
  missionType: 'CAPTURE'
  targetId: string
  uavIds: string[]
  usvIds: string[]
  captureRadius: number
  minimumAgents: number
  dynamicReassignment: boolean
}

export interface EscortDefenseAlgorithmStartRequest {
  missionType: 'ESCORT_DEFENSE'
  escortTargetId: string
  threatTargetId: string
  uavIds: string[]
  usvIds: string[]
  escortRadius: number
  defenseDistance: number
  threatDirection: string
}

export type AlgorithmStartRequest =
  | CaptureAlgorithmStartRequest
  | EscortDefenseAlgorithmStartRequest

export interface AlgorithmCommandResult {
  runId: string
  commandId: string
  accepted: boolean
  status: string
  message: string
  requestedAt: string
}

export interface AlgorithmStopRequest {
  runId: string
}

export interface AlgorithmResetRequest {
  runId: string | null
}

export interface AlgorithmMissionSnapshot {
  summary: AlgorithmMissionSummary
  scene: AlgorithmTacticalScene
  assignments: AlgorithmAssignment[]
  events: AlgorithmEvent[]
  refreshedAt: string
}