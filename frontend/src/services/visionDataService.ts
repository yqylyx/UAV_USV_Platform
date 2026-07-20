import type {
    VisionCameraSource,
    VisionDetection,
    VisionSensorStatus,
  } from '@/types/vision'
  
  const mockSensorStatuses: VisionSensorStatus[] = [
    {
      vehicleId: 'uav_01',
      sensorId: 'front_camera',
      sensorType: 'CAMERA',
      online: true,
      healthy: true,
      measuredRateHz: 20,
      latencyMs: 36,
      tfAvailable: true,
      lastUpdateTime: '2026-07-20 10:30:05',
    },
    {
      vehicleId: 'usv_01',
      sensorId: 'mid360',
      sensorType: 'LIDAR',
      online: true,
      healthy: false,
      measuredRateHz: 6.8,
      latencyMs: 185,
      tfAvailable: false,
      lastUpdateTime: '2026-07-20 10:29:58',
    },
    {
      vehicleId: 'uav_02',
      sensorId: 'down_camera',
      sensorType: 'CAMERA',
      online: null,
      healthy: null,
      measuredRateHz: null,
      latencyMs: null,
      tfAvailable: null,
      lastUpdateTime: null,
    },
  ]
  
  const mockDetections: VisionDetection[] = [
    {
      trackId: 'target_01',
      className: '无人艇',
      sensorSource: 'uav_01/front_camera',
      sourceLabel: '相机',
      affiliation: 'HOSTILE',
      classConfidence: 0.92,
      x: 125.6,
      y: 78.3,
      speedX: 3.2,
      speedY: 1.4,
      lastUpdateTime: '2026-07-20 10:30:05',
    },
    {
      trackId: 'target_02',
      className: '船只',
      sensorSource: 'usv_01/mid360',
      sourceLabel: '激光雷达',
      affiliation: 'UNKNOWN',
      classConfidence: 0.81,
      x: 86.4,
      y: 142.7,
      speedX: 1.1,
      speedY: -0.6,
      lastUpdateTime: '2026-07-20 10:30:02',
    },
    {
      trackId: 'target_03',
      className: '浮标',
      sensorSource: 'camera_lidar_fusion',
      sourceLabel: '相机+激光雷达',
      affiliation: 'NEUTRAL',
      classConfidence: 0.76,
      x: 53.8,
      y: 94.2,
      speedX: 0,
      speedY: 0,
      lastUpdateTime: '2026-07-20 10:29:58',
    },
  ]
  
  const mockCameraSources: VisionCameraSource[] = [
    {
      vehicleId: 'uav_01',
      sensorId: 'front_camera',
      displayName: 'UAV-01 前视相机',
      topic: '/fleet/uplink/uav_01/camera/image_raw',
      online: true,
      streamUrl: null,
    },
    {
      vehicleId: 'uav_02',
      sensorId: 'down_camera',
      displayName: 'UAV-02 下视相机',
      topic: '/fleet/uplink/uav_02/camera/image_raw',
      online: false,
      streamUrl: null,
    },
  ]
  
  export function getVisionSensorStatuses(): VisionSensorStatus[] {
    return mockSensorStatuses
  }
  
  export function getVisionDetections(): VisionDetection[] {
    return mockDetections
  }
  
  export function getVisionCameraSources(): VisionCameraSource[] {
    return mockCameraSources
  }