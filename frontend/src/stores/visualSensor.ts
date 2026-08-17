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
  VisualSensorRuntimeContext,
  VisualSensorRuntimeScope,
  VisualSensorViewType,
} from '@/types/visualSensor'

const UNITY_FRAME_FRESH_MS = 15_000
const UNITY_STREAM_FRESH_MS = 4_000
const BACKEND_FRAME_FRESH_MS = 4_000

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

interface VisualSensorChannelState {
  overview: VisualSensorOverview | null
  frameUrls: Record<string, string>
  frameReceivedAtMs: Record<string, number>
  unityFrames: Record<string, UnityVisualSensorMeta>
  streamStats: UnityVisualSensorStreamStats | null
  unityBridgeReady: boolean
  framesRefreshing: boolean
  unityFocusedCameraId: string
  context: VisualSensorRuntimeContext
}

interface VisualSensorState {
  channels: Record<VisualSensorRuntimeScope, VisualSensorChannelState>
  loading: boolean
  error: string
}

function fallbackOverview(focusedCameraId = 'uav_01'): VisualSensorOverview {
  return {
    gatewayConnected: false,
    gatewayDetail: '等待 Unity WebGL 视觉桥',
    onlineCount: 0,
    totalCount: SENSOR_CATALOG.length,
    focusedCameraId,
    sensors: SENSOR_CATALOG.map((sensor) => ({
      ...sensor,
      status: 'WAITING',
      source: 'Unity WebGL',
      width: 0,
      height: 0,
      fps: 0,
      latencyMs: -1,
      timestampMs: 0,
      focused: sensor.cameraId === focusedCameraId,
    })),
  }
}

function createContext(runtimeScope: VisualSensorRuntimeScope): VisualSensorRuntimeContext {
  return {
    runtimeScope,
    runtimeInstanceId: runtimeScope === 'SYSTEM_OVERVIEW' ? 'overview-unity-01' : '',
    missionId: null,
    runId: null,
  }
}

function createChannel(runtimeScope: VisualSensorRuntimeScope): VisualSensorChannelState {
  return {
    overview: null,
    frameUrls: {},
    frameReceivedAtMs: {},
    unityFrames: {},
    streamStats: null,
    unityBridgeReady: false,
    framesRefreshing: false,
    unityFocusedCameraId: 'uav_01',
    context: createContext(runtimeScope),
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

function releaseChannelFrames(channel: VisualSensorChannelState) {
  Object.values(channel.frameUrls).forEach((url) => URL.revokeObjectURL(url))
  channel.frameUrls = {}
  channel.frameReceivedAtMs = {}
  channel.unityFrames = {}
  channel.streamStats = null
}

function contextKey(context: VisualSensorRuntimeContext) {
  return [
    context.runtimeScope,
    context.runtimeInstanceId,
    context.missionId ?? '',
    context.runId ?? '',
  ].join(':')
}

function payloadMatchesContext(
  channel: VisualSensorChannelState,
  payload: Record<string, unknown>,
) {
  if (channel.context.runtimeScope === 'SYSTEM_OVERVIEW') return true
  const payloadInstanceId = String(payload.runtimeInstanceId ?? '')
  if (
    payloadInstanceId
    && channel.context.runtimeInstanceId
    && payloadInstanceId !== channel.context.runtimeInstanceId
  ) return false
  const payloadRunId = payload.runId
  if (
    channel.context.runId !== null
    && payloadRunId !== undefined
    && payloadRunId !== null
    && String(payloadRunId) !== ''
    && Number(payloadRunId) !== channel.context.runId
  ) return false
  return true
}

function buildDisplayOverview(channel: VisualSensorChannelState): VisualSensorOverview {
  const base = channel.overview ?? fallbackOverview(channel.unityFocusedCameraId)
  const fallback = fallbackOverview(channel.unityFocusedCameraId)
  const backendSensors = new Map(base.sensors.map((sensor) => [sensor.cameraId, sensor]))
  const now = Date.now()
  const directStream = channel.streamStats
  const directStreamFresh = !!directStream
    && channel.unityBridgeReady
    && directStream.active
    && directStream.gpuDirect
    && now - directStream.receivedAtMs <= UNITY_STREAM_FRESH_MS
  const sensors = fallback.sensors.map((fallbackSensor): VisualSensor => {
    const sensor = {
      ...fallbackSensor,
      ...backendSensors.get(fallbackSensor.cameraId),
    }
    if (
      directStreamFresh
      && (directStream.displayMode === 'grid' || sensor.cameraId === directStream.focusedCameraId)
    ) {
      return {
        ...sensor,
        status: 'ONLINE',
        source: 'Unity WebGL GPU Direct',
        width: directStream.streamWidth,
        height: directStream.streamHeight,
        fps: directStream.measuredFps || directStream.targetFps,
        latencyMs: Math.max(0, Math.round(directStream.renderMs)),
        timestampMs: directStream.timestampMs,
        focused: sensor.cameraId === channel.unityFocusedCameraId,
      }
    }
    const unity = channel.unityFrames[sensor.cameraId]
    const fresh = !!unity && now - unity.receivedAtMs <= UNITY_FRAME_FRESH_MS
    if (!fresh) {
      return {
        ...sensor,
        focused: sensor.cameraId === channel.unityFocusedCameraId,
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
      focused: sensor.cameraId === channel.unityFocusedCameraId,
    }
  })
  const unityOnline = sensors.filter((sensor) => sensor.status === 'ONLINE').length
  return {
    ...base,
    gatewayConnected: channel.unityBridgeReady || base.gatewayConnected,
    gatewayDetail: directStreamFresh
      ? `Unity GPU 六路直出 · ${directStream.activeQuality.toUpperCase()}`
      : channel.unityBridgeReady
        ? 'Unity WebGL 六路视觉桥在线'
        : base.gatewayConnected
          ? base.gatewayDetail
          : 'Unity WebGL 设备相机初始化中',
    onlineCount: Math.max(base.onlineCount, unityOnline),
    totalCount: SENSOR_CATALOG.length,
    focusedCameraId: channel.unityFocusedCameraId,
    sensors,
  }
}

export const useVisualSensorStore = defineStore('visual-sensor', {
  state: (): VisualSensorState => ({
    channels: {
      SYSTEM_OVERVIEW: createChannel('SYSTEM_OVERVIEW'),
      MISSION_CENTER: createChannel('MISSION_CENTER'),
    },
    loading: false,
    error: '',
  }),
  getters: {
    displayOverview: (state) => buildDisplayOverview(state.channels.SYSTEM_OVERVIEW),
    streamStats: (state) => state.channels.SYSTEM_OVERVIEW.streamStats,
    unityBridgeReady: (state) => state.channels.SYSTEM_OVERVIEW.unityBridgeReady,
    displayOverviewFor: (state) => (scope: VisualSensorRuntimeScope) =>
      buildDisplayOverview(state.channels[scope]),
    streamStatsFor: (state) => (scope: VisualSensorRuntimeScope) =>
      state.channels[scope].streamStats,
    unityBridgeReadyFor: (state) => (scope: VisualSensorRuntimeScope) =>
      state.channels[scope].unityBridgeReady,
    runtimeContextFor: (state) => (scope: VisualSensorRuntimeScope) =>
      state.channels[scope].context,
  },
  actions: {
    bindRuntime(context: VisualSensorRuntimeContext) {
      const channel = this.channels[context.runtimeScope]
      if (contextKey(channel.context) === contextKey(context)) return
      releaseChannelFrames(channel)
      channel.overview = context.runtimeScope === 'SYSTEM_OVERVIEW' ? channel.overview : null
      channel.unityFocusedCameraId = 'uav_01'
      channel.context = { ...context }
    },
    async refreshOverview() {
      try {
        this.channels.SYSTEM_OVERVIEW.overview = await fetchVisualSensors()
        this.error = ''
      } catch {
        if (!this.channels.SYSTEM_OVERVIEW.overview) {
          this.channels.SYSTEM_OVERVIEW.overview = fallbackOverview()
        }
        // The backend gateway is an optional system-overview fallback.
      }
    },
    async select(cameraId: string) {
      return this.selectFor('SYSTEM_OVERVIEW', cameraId)
    },
    async selectFor(scope: VisualSensorRuntimeScope, cameraId: string) {
      const channel = this.channels[scope]
      channel.unityFocusedCameraId = cameraId
      if (scope !== 'SYSTEM_OVERVIEW') return
      try {
        channel.overview = await focusVisualSensor(cameraId)
        this.error = ''
      } catch {
        // Keep the local Unity selection; backend focus is only a fallback.
      }
    },
    markUnityBridgeReady(
      scope: VisualSensorRuntimeScope,
      ready = true,
      context?: VisualSensorRuntimeContext,
    ) {
      if (context) this.bindRuntime(context)
      const channel = this.channels[scope]
      channel.unityBridgeReady = ready
      if (ready) this.error = ''
    },
    ingestUnityFrame(
      scope: VisualSensorRuntimeScope,
      payload: Record<string, unknown>,
      context?: VisualSensorRuntimeContext,
    ) {
      if (context) this.bindRuntime(context)
      const channel = this.channels[scope]
      if (!payloadMatchesContext(channel, payload)) return
      const frame = payload as unknown as UnityVisualSensorFrame
      if (!SENSOR_CATALOG.some((sensor) => sensor.cameraId === frame.cameraId)) return
      if (!frame.jpegBase64 || frame.width <= 0 || frame.height <= 0) return
      try {
        const now = Date.now()
        const previous = channel.unityFrames[frame.cameraId]
        const interval = previous ? now - previous.receivedAtMs : 0
        const instantFps = interval > 0 ? 1_000 / interval : 0
        const fps = previous?.fps
          ? previous.fps * 0.72 + instantFps * 0.28
          : instantFps
        const nextUrl = URL.createObjectURL(decodeJpeg(frame.jpegBase64))
        const previousUrl = channel.frameUrls[frame.cameraId]
        channel.frameUrls[frame.cameraId] = nextUrl
        if (previousUrl) URL.revokeObjectURL(previousUrl)
        channel.unityFrames[frame.cameraId] = {
          width: frame.width,
          height: frame.height,
          fps,
          timestampMs: frame.timestampMs || now,
          receivedAtMs: now,
          sequence: frame.sequence,
          source: frame.source || 'Unity WebGL',
        }
        channel.unityBridgeReady = true
        this.error = ''
      } catch {
        // Ignore a malformed frame and keep the last valid Unity image.
      }
    },
    ingestUnityStreamStats(
      scope: VisualSensorRuntimeScope,
      payload: Record<string, unknown>,
      context?: VisualSensorRuntimeContext,
    ) {
      if (context) this.bindRuntime(context)
      const channel = this.channels[scope]
      if (!payloadMatchesContext(channel, payload)) return
      const stats = payload as unknown as Omit<UnityVisualSensorStreamStats, 'receivedAtMs'>
      if (!stats || typeof stats.active !== 'boolean') return
      channel.streamStats = {
        ...stats,
        receivedAtMs: Date.now(),
      }
      if (stats.focusedCameraId) channel.unityFocusedCameraId = stats.focusedCameraId
      channel.unityBridgeReady = stats.gpuDirect === true || channel.unityBridgeReady
      this.error = ''
    },
    hasFreshUnityFrame(cameraId: string, scope: VisualSensorRuntimeScope = 'SYSTEM_OVERVIEW') {
      const frame = this.channels[scope].unityFrames[cameraId]
      return !!frame && Date.now() - frame.receivedAtMs <= UNITY_FRAME_FRESH_MS
    },
    hasFreshBackendFrame(cameraId: string, scope: VisualSensorRuntimeScope = 'SYSTEM_OVERVIEW') {
      const receivedAtMs = this.channels[scope].frameReceivedAtMs[cameraId] ?? 0
      return receivedAtMs > 0 && Date.now() - receivedAtMs <= BACKEND_FRAME_FRESH_MS
    },
    async refreshFrames(
      focusedOnly = false,
      scope: VisualSensorRuntimeScope = 'SYSTEM_OVERVIEW',
    ) {
      // Mission-center vision is always read from its own live Unity canvas.
      // The global backend JPEG endpoint is not run-scoped and must not be used.
      if (scope !== 'SYSTEM_OVERVIEW') return
      const channel = this.channels[scope]
      if (channel.framesRefreshing) return
      channel.framesRefreshing = true
      const sensors = buildDisplayOverview(channel).sensors
      const targets = focusedOnly
        ? sensors.filter((sensor) => sensor.cameraId === channel.unityFocusedCameraId)
        : sensors
      try {
        await Promise.all(targets.map(async (sensor) => {
          if (
            this.hasFreshUnityFrame(sensor.cameraId, scope)
            || this.hasFreshBackendFrame(sensor.cameraId, scope)
          ) return
          try {
            const blob = await fetchVisualSensorFrame(sensor.cameraId)
            if (!blob) return
            const nextUrl = URL.createObjectURL(blob)
            const previousUrl = channel.frameUrls[sensor.cameraId]
            channel.frameUrls[sensor.cameraId] = nextUrl
            channel.frameReceivedAtMs[sensor.cameraId] = Date.now()
            if (previousUrl) URL.revokeObjectURL(previousUrl)
          } catch {
            // Keep the last valid Unity or ROS frame during a short interruption.
          }
        }))
      } finally {
        channel.framesRefreshing = false
      }
    },
    disposeFrames(scope: VisualSensorRuntimeScope = 'SYSTEM_OVERVIEW') {
      const channel = this.channels[scope]
      releaseChannelFrames(channel)
      channel.unityBridgeReady = false
    },
  },
})
