import { http } from './http'
import type { ApiResponse } from '@/types/api'

export type SensorType = 'CAMERA' | 'LIDAR' | 'CAMERA_LIDAR'
export type TargetType = 'ENEMY_USV' | 'ENEMY_UAV' | 'FRIENDLY_USV' | 'FRIENDLY_UAV' | 'UNKNOWN' | 'OBSTACLE'
export type TargetSource = 'CAMERA' | 'LIDAR' | 'CAMERA_LIDAR' | 'ALGORITHM' | 'SIMULATION'
export type Affiliation = 'HOSTILE' | 'FRIENDLY' | 'NEUTRAL' | 'UNKNOWN'

export interface PerceptionSensor {
  vehicleId: string
  vehicleCode: string
  sensorType: SensorType
  online: boolean
  healthy: boolean
  frequency: number | null
  latency: number | null
  imageUrl: string | null
  detail: string | null
  lastUpdateTime: string
}

export interface PerceptionTarget {
  targetId: string
  targetType: TargetType
  source: TargetSource
  x: number
  y: number
  z: number
  confidence: number
  affiliation: Affiliation
  detectedBy: string | null
  lastUpdateTime: string
}

export async function fetchPerceptionSensors(): Promise<PerceptionSensor[]> {
  const response = await http.get<ApiResponse<PerceptionSensor[]>>('/perception/sensors')
  return response.data.data
}

export async function fetchPerceptionTargets(): Promise<PerceptionTarget[]> {
  const response = await http.get<ApiResponse<PerceptionTarget[]>>('/perception/targets')
  return response.data.data
}
