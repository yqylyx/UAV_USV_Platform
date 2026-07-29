import { defineStore } from 'pinia'

import {
  fetchVisualSensorFrame,
  fetchVisualSensors,
  focusVisualSensor,
} from '@/api/visualSensor'
import type {
  UnityVisualSensorFrame,
  UnityVisualSensorMeta,
  UnityVisualSensorStreamStats,
  VisualSensor,
  VisualSensorOverview,
  VisualSensorViewType,
} from '@/types/visualSensor'

const UNITY_FRAME_FRESH_MS = 15_000
const UNITY_STREAM_FRESH_MS = 4_000

const SENSOR_CATALOG: Array<{
  cameraId: string
  deviceCode: string
  deviceType: 'UAV' | 'USV'
  viewType: VisualSensorViewType
  displayName: string
}> = [
  { cameraId: 'uav_01', deviceCode: 'UAV-01', deviceType: 'UAV', viewType: 'DOWN', displayName: 'UAV-01 · 下视相机' },
  { cameraId: 'uav_02', deviceCode: 'UAV-02', deviceType: 'UAV', viewType: 'DOWN', displayName: 'UAV-02 · 下视相机' },
  { cameraId: 'uav_03', deviceCode: 'UAV-03', deviceType: 'UAV', viewType: 'DOWN', displayName: 'UAV-03 · 下视相机' },
  { cameraId: 'usv_01', deviceCode: 'USV-01', deviceType: 'USV', viewType: 'FORWARD', displayName: 'USV-01 · 前视相机' },
  { cameraId: 'usv_02', deviceCode: 'USV-02', deviceType: 'USV', viewType: 'FORWARD', displayName: 'USV-02 · 前视相机' },
  { cameraId: 'usv_03', deviceCode: 'USV-03', deviceType: 'USV', viewType: 'FORWARD', displayName: 'USV-03 · 前视相机' },
]

function fallbackOverview(): VisualSensorOverview {
  return {
    gatewayConnected: false,
    gatewayDetail: '等待 Unity WebGL 视觉桥',
    onlineCount: 0,
    totalCount: SENSOR_CATALOG.length,
    focusedCameraId: 'uav_01',
    sensors: SENSOR_CATALOG.map((sensor) => ({
      ...sensor,
      status: 'WAITING',
      source: 'Unity WebGL',
      width: 0,
      height: 0,
      fps: 0,
      latencyMs: -1,
      timestampMs: 0,
      focused: sensor.cameraId === 'uav_01',
    })),
  }
}

function decodeJpeg(jpegBase64: string) {
  const binary = window.atob(jpegBase64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new Blob([bytes], { type: 'image/jpeg' })
}

interface VisualSensorState {
  overview: VisualSensorOverview | null
  frameUrls: Record<string, string>
  unityFrames: Record<string, UnityVisualSensorMeta>
  streamStats: UnityVisualSensorStreamStats | null
  unityBridgeReady: boolean
  unityFocusedCameraId: string
  loading: boolean
  error: string
}

export const useVisualSensorStore = defineStore('visual-sensor', {
  state: (): VisualSensorState => ({
    overview: null,
    frameUrls: {},
    unityFrames: {},
    streamStats: null,
    unityBridgeReady: false,
    unityFocusedCameraId: 'uav_01',
    loading: false,
    error: '',
  }),
  getters: {
    displayOverview(state): VisualSensorOverview {
      const base = state.overview ?? fallbackOverview()
      const fallback = fallbackOverview()
      const backendSensors = new Map(
        base.sensors.map((sensor) => [sensor.cameraId, sensor]),
      )
      const now = Date.now()
      const directStream = state.streamStats
      const directStreamFresh = !!directStream
        && directStream.active
        && directStream.gpuDirect
        && now - directStream.receivedAtMs <= UNITY_STREAM_FRESH_MS
      const sensors = fallback.sensors.map((fallbackSensor): VisualSensor => {
        const sensor = {
          ...fallbackSensor,
          ...backendSensors.get(fallbackSensor.cameraId),
        }
        if (directStreamFresh) {
          return {
            ...sensor,
            status: 'ONLINE',
            source: 'Unity WebGL GPU Direct',
            width: directStream.streamWidth,
            height: directStream.streamHeight,
            fps: directStream.measuredFps || directStream.targetFps,
            latencyMs: Math.max(0, Math.round(directStream.renderMs)),
            timestampMs: directStream.timestampMs,
            focused: sensor.cameraId === state.unityFocusedCameraId,
          }
        }
        const unity = state.unityFrames[sensor.cameraId]
        const fresh = !!unity && now - unity.receivedAtMs <= UNITY_FRAME_FRESH_MS
        if (!fresh) {
          return {
            ...sensor,
            focused: sensor.cameraId === state.unityFocusedCameraId,
          }
        }
        return {
          ...sensor,
          status: 'ONLINE',
          source: unity.source,
          width: unity.width,
          height: unity.height,
          fps: unity.fps,
          latencyMs: Math.max(0, now - unity.timestampMs),
          timestampMs: unity.timestampMs,
          focused: sensor.cameraId === state.unityFocusedCameraId,
        }
      })
      const unityOnline = directStreamFresh ? SENSOR_CATALOG.length : sensors.filter((sensor) => {
        const frame = state.unityFrames[sensor.cameraId]
        return !!frame && now - frame.receivedAtMs <= UNITY_FRAME_FRESH_MS
      }).length
      return {
        ...base,
        gatewayConnected: state.unityBridgeReady || base.gatewayConnected,
        gatewayDetail: directStreamFresh
          ? `Unity GPU 六路直出 · ${directStream.activeQuality.toUpperCase()}`
          : state.unityBridgeReady
            ? 'Unity WebGL 六路视觉桥在线'
          : 'Unity WebGL 设备相机初始化中',
        onlineCount: Math.max(base.onlineCount, unityOnline),
        totalCount: SENSOR_CATALOG.length,
        focusedCameraId: state.unityFocusedCameraId,
        sensors,
      }
    },
  },
  actions: {
    async refreshOverview() {
      try {
        this.overview = await fetchVisualSensors()
        this.error = ''
      } catch {
        if (!this.overview) this.overview = fallbackOverview()
        // The backend gateway is an optional fallback. Unity WebGL frames must
        // remain usable when ROS or the backend visual gateway is unavailable.
      }
    },
    async select(cameraId: string) {
      this.unityFocusedCameraId = cameraId
      try {
        this.overview = await focusVisualSensor(cameraId)
        this.error = ''
      } catch {
        // Keep the local Unity selection; backend focus is only a fallback.
      }
    },
    markUnityBridgeReady(ready = true) {
      this.unityBridgeReady = ready
      if (ready) this.error = ''
    },
    ingestUnityFrame(payload: Record<string, unknown>) {
      const frame = payload as unknown as UnityVisualSensorFrame
      if (!SENSOR_CATALOG.some((sensor) => sensor.cameraId === frame.cameraId)) return
      if (!frame.jpegBase64 || frame.width <= 0 || frame.height <= 0) return
      try {
        const now = Date.now()
        const previous = this.unityFrames[frame.cameraId]
        const interval = previous ? now - previous.receivedAtMs : 0
        const instantFps = interval > 0 ? 1_000 / interval : 0
        const fps = previous?.fps
          ? previous.fps * 0.72 + instantFps * 0.28
          : instantFps
        const nextUrl = URL.createObjectURL(decodeJpeg(frame.jpegBase64))
        const previousUrl = this.frameUrls[frame.cameraId]
        this.frameUrls[frame.cameraId] = nextUrl
        if (previousUrl) URL.revokeObjectURL(previousUrl)
        this.unityFrames[frame.cameraId] = {
          width: frame.width,
          height: frame.height,
          fps,
          timestampMs: frame.timestampMs || now,
          receivedAtMs: now,
          sequence: frame.sequence,
          source: frame.source || 'Unity WebGL',
        }
        this.unityBridgeReady = true
        this.error = ''
      } catch {
        // Ignore a malformed frame and keep the last valid Unity image.
      }
    },
    ingestUnityStreamStats(payload: Record<string, unknown>) {
      const stats = payload as unknown as Omit<UnityVisualSensorStreamStats, 'receivedAtMs'>
      if (!stats || typeof stats.active !== 'boolean') return
      this.streamStats = {
        ...stats,
        receivedAtMs: Date.now(),
      }
      if (stats.focusedCameraId) this.unityFocusedCameraId = stats.focusedCameraId
      this.unityBridgeReady = stats.gpuDirect === true || this.unityBridgeReady
      this.error = ''
    },
    hasFreshUnityFrame(cameraId: string) {
      const frame = this.unityFrames[cameraId]
      return !!frame && Date.now() - frame.receivedAtMs <= UNITY_FRAME_FRESH_MS
    },
    async refreshFrames(focusedOnly = false) {
      const sensors = this.displayOverview.sensors
      const targets = focusedOnly
        ? sensors.filter((sensor) => sensor.cameraId === this.unityFocusedCameraId)
        : sensors
      await Promise.all(targets.map(async (sensor) => {
        if (this.hasFreshUnityFrame(sensor.cameraId)) return
        try {
          const blob = await fetchVisualSensorFrame(sensor.cameraId)
          if (!blob) return
          const nextUrl = URL.createObjectURL(blob)
          const previousUrl = this.frameUrls[sensor.cameraId]
          this.frameUrls[sensor.cameraId] = nextUrl
          if (previousUrl) URL.revokeObjectURL(previousUrl)
        } catch {
          // Keep the last valid Unity or ROS frame during a short interruption.
        }
      }))
    },
    disposeFrames() {
      Object.values(this.frameUrls).forEach((url) => URL.revokeObjectURL(url))
      this.frameUrls = {}
      this.unityFrames = {}
      this.streamStats = null
      this.unityBridgeReady = false
    },
  },
})
