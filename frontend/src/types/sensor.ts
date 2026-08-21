export interface RadarItem {
  id: string
  deviceId: string
  kind: 'OBSTACLE' | 'DETECTION' | 'POINTCLOUD' | 'RADAR_RETURN'
  range: number | null
  bearing: number | null
  x: number | null
  y: number | null
  z: number | null
  confidence: number | null
  timestampMs: number
}

export interface RadarOverview {
  connected: boolean
  onlineCount: number
  totalCount: number
  updatedAt: number
  obstacleCount: number
  detectionCount: number
  nearestObstacleRange: number | null
  latestTargetId: string
  items: RadarItem[]
}
