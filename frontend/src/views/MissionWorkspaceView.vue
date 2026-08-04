<script setup lang="ts">
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  Box,
  Camera,
  CircleCheck,
  Clock3,
  Layers3,
  Pause,
  Play,
  Radio,
  Settings2,
  Square,
  XOctagon,
} from '@lucide/vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import AlgorithmManagerDialog from '@/components/mission/AlgorithmManagerDialog.vue'
import AlgorithmTrajectoryMap from '@/components/mission/AlgorithmTrajectoryMap.vue'
import MissionEventDrawer from '@/components/mission/MissionEventDrawer.vue'
import MissionTrajectoryMap from '@/components/mission/MissionTrajectoryMap.vue'
import {
  controlAlgorithmRun,
  fetchAlgorithmFrames,
  fetchAlgorithms,
  placeEscortThreat,
  prepareAlgorithmRun,
  setAlgorithmEnabled,
  setDefaultAlgorithm,
} from '@/api/algorithm'
import {
  executeMissionAction,
  fetchMission,
  fetchMissionPreflight,
} from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import { useMissionStore } from '@/stores/mission'
import { useMissionTrajectorySessionStore } from '@/stores/missionTrajectorySession'
import { useMonitoringStore } from '@/stores/monitoring'
import { useRadarSensorStore } from '@/stores/radarSensor'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useUnityViewportStore } from '@/stores/unityViewport'
import { useVisualSensorStore } from '@/stores/visualSensor'
import type {
  AlgorithmDefinition,
  AlgorithmRuntimeFrame,
  Mission,
  MissionDetail,
} from '@/types/mission'
import type { RuntimeNode } from '@/types/monitoring'
import type { RadarOverview } from '@/types/sensor'
import type { VisualSensorRuntimeContext } from '@/types/visualSensor'

type WorkspaceMode = '2d' | '3d' | 'vision' | 'radar'
type VisualDisplayMode = 'grid' | 'focus'

const route = useRoute()
const router = useRouter()
const missionStore = useMissionStore()
const monitoringStore = useMonitoringStore()
const radarStore = useRadarSensorStore()
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
const sessionStore = useMissionTrajectorySessionStore()
const unityViewportStore = useUnityViewportStore()
const visualSensorStore = useVisualSensorStore()
let radarTimer: number | undefined

const radarOverview = computed<RadarOverview>(() => radarStore.overview ?? {
  connected: false,
  onlineCount: 0,
  totalCount: 0,
  updatedAt: 0,
  obstacleCount: 0,
  detectionCount: 0,
  nearestObstacleRange: null,
  latestTargetId: '',
  items: [],
})
const radarItems = computed(() => radarOverview.value.items.slice(0, 6))
const radarPlotPoints = computed(() => {
  const points = radarOverview.value.items
    .filter(item => item.kind === 'POINTCLOUD' && item.x != null && item.y != null)
    .slice(0, 240)
  if (points.length === 0) return []
  const maxAbs = Math.max(1, ...points.flatMap(item => [Math.abs(item.x ?? 0), Math.abs(item.y ?? 0)]))
  const scale = 44 / maxAbs
  return points.map(item => ({
    id: item.id,
    cx: 50 + (item.y ?? 0) * scale,
    cy: 50 - (item.x ?? 0) * scale,
    range: item.range,
  }))
})

const detail = ref<MissionDetail | null>(null)
const algorithms = ref<AlgorithmDefinition[]>([])
const selectedAlgorithmCode = ref('GB_SFLA_CS')
const selectedDeviceCode = ref('')
const mode = ref<WorkspaceMode>('2d')
const visualDisplayMode = ref<VisualDisplayMode>('grid')
const busy = ref(false)
const loading = ref(true)
const algorithmBusy = ref(false)
const algorithmManagerVisible = ref(false)
const eventVisible = ref(false)
const algorithmFrame = ref<AlgorithmRuntimeFrame | null>(null)
const algorithmPolling = ref(false)

const unityChannel = computed(() => unityBridgeStore.channels.MISSION_CENTER)
const trajectoryFrame = computed(() => trajectoryStore.channels.MISSION_CENTER.frame)
const currentRunId = computed(() => detail.value?.currentRun?.id ?? null)
const activeAlgorithmCode = computed(() => detail.value?.mission.algorithmCode ?? '')
const activeMission = computed(() => detail.value?.mission ?? null)
const activeRun = computed(() => ['RUNNING', 'PAUSED'].includes(activeMission.value?.status ?? ''))
const rosOnline = computed(() =>
  monitoringStore.nodes.some(node => node.type === 'ROS_NODE' && node.status === 'ONLINE'),
)
const enabledAlgorithms = computed(() =>
  algorithms.value.filter(item => item.enabled && ['GB_SFLA_CS', 'ESCORT_GUARD'].includes(item.code)),
)
const currentAlgorithm = computed(() =>
  algorithms.value.find(item => item.code === selectedAlgorithmCode.value) ?? null,
)
const onlineVehicleCount = computed(() =>
  runtimeNodes.value.filter(node => node.status === 'ONLINE').length,
)
const statusLabel = computed(() => {
  const status = activeMission.value?.status
  if (status === 'RUNNING') return '运行中'
  if (status === 'PAUSED') return '已暂停'
  if (status === 'COMPLETED') return '已完成'
  if (status === 'FAILED') return '异常'
  if (status === 'CANCELLED') return '已终止'
  return '待执行'
})
const primaryActionLabel = computed(() => {
  if (busy.value) return '处理中'
  if (activeRun.value && selectedAlgorithmCode.value !== activeAlgorithmCode.value) return '切换并执行'
  if (activeRun.value) return '重新执行'
  return '开始任务'
})
const recentEvents = computed(() => detail.value?.events.slice(0, 3) ?? [])
const missionVisualStats = computed(() => visualSensorStore.streamStatsFor('MISSION_CENTER'))
const missionVisualConnected = computed(() =>
  visualSensorStore.unityBridgeReadyFor('MISSION_CENTER')
  && missionVisualStats.value?.active === true
  && visualSensorStore.runtimeContextFor('MISSION_CENTER').runId === currentRunId.value,
)
const unityRunSynchronized = computed(() =>
  currentRunId.value !== null
  && unityChannel.value.appliedRunId === currentRunId.value
  && !!algorithmFrame.value
  && unityChannel.value.appliedSequence >= algorithmFrame.value.sequence,
)
const runSyncText = computed(() => {
  if (!detail.value?.currentRun) return '等待创建 RUN'
  if (mode.value === 'vision') return missionVisualConnected.value ? '六路任务视觉已连接' : '任务视觉连接中'
  if (mode.value === '3d' && !unityRunSynchronized.value) return '3D 正在同步当前 RUN'
  return `RUN ${detail.value.currentRun.runNo} · 同步帧 ${algorithmFrame.value?.sequence ?? 0}`
})
const sceneScale = computed(() =>
  selectedAlgorithmCode.value === 'ESCORT_GUARD'
    ? '3 UAV + 3 USV + 1 Escort'
    : '3 UAV + 3 USV + 1 Target',
)

let algorithmPollTimer: number | null = null
let algorithmAbortController: AbortController | null = null
let loadedScenarioKey = ''
let algorithmRecoveryPromise: Promise<void> | null = null

const runtimeNodes = computed<RuntimeNode[]>(() => {
  const frame = trajectoryFrame.value
  if (!frame) {
    return monitoringStore.nodes.filter(node => node.type === 'UAV' || node.type === 'USV')
  }
  return frame.agents
    .filter(agent => agent.type === 'UAV' || agent.type === 'USV')
    .map((agent, index) => {
      const existing = monitoringStore.nodes.find(
        node => node.code.toLowerCase() === agent.code.toLowerCase(),
      )
      return {
        id: existing?.id ?? -(index + 1),
        code: agent.code,
        name: existing?.name ?? `协同${agent.type === 'UAV' ? '无人机' : '无人艇'} ${agent.code.replace(/[^0-9]/g, '')}`,
        type: agent.type as 'UAV' | 'USV',
        status: 'ONLINE',
        host: null,
        port: null,
        endpoint: 'unity://mission-center',
        rosNamespace: null,
        lastHeartbeatAt: new Date(frame.receivedAt).toISOString(),
        heartbeatAgeSeconds: Math.max(0, Math.round((Date.now() - frame.receivedAt) / 1000)),
        source: 'UNITY_WEBGL',
        instanceId: unityViewportStore.missionInstanceId,
        positionX: agent.x,
        positionY: agent.y,
        positionZ: agent.z,
        detail: agent.state,
      }
    })
})

function queryNumber(value: unknown) {
  const parsed = Number(Array.isArray(value) ? value[0] : value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function requestedViewMode(): WorkspaceMode {
  if (route.query.view === 'radar') return 'radar'
  if (route.query.view === 'vision') return 'vision'
  if (route.query.view === '3d') return '3d'
  return '2d'
}

function formatRadarRange(value: number | null) {
  return value == null ? '-- m' : `${value.toFixed(1)} m`
}

function formatRadarTime(value: number) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

function stopRadarPolling() {
  if (radarTimer) window.clearInterval(radarTimer)
  radarTimer = undefined
}

function startRadarPolling() {
  stopRadarPolling()
  void radarStore.refresh(true)
  radarTimer = window.setInterval(() => void radarStore.refresh(true), 2500)
}

function missionForAlgorithm(code: string) {
  return missionStore.records.find(mission => mission.algorithmCode === code) ?? null
}

function currentAlgorithmConfig() {
  return Object.fromEntries(
    (detail.value?.parameters ?? []).map(item => [item.key, item.value ?? '']),
  )
}

function missionUnityCommand(action: MissionAction) {
  return {
    start: 'missionStart',
    pause: 'missionPause',
    resume: 'missionResume',
    complete: 'missionComplete',
    fail: 'missionFail',
    cancel: 'missionCancel',
    ready: 'missionResume',
  }[action]
}

function missionVisualContext(): VisualSensorRuntimeContext {
  return {
    runtimeScope: 'MISSION_CENTER',
    runtimeInstanceId: unityViewportStore.missionInstanceId,
    missionId: detail.value?.mission.id ?? null,
    runId: currentRunId.value,
  }
}

function cameraIdForDevice(deviceCode: string) {
  return deviceCode.trim().toLowerCase().replace(/-/g, '_')
}

function sendMissionVisualSubscription(
  enabled: boolean,
  displayMode: 'grid' | 'focus' | 'off' = visualDisplayMode.value,
) {
  const context = missionVisualContext()
  if (context.missionId === null || context.runId === null) return
  visualSensorStore.bindRuntime(context)
  const focusedCameraId = cameraIdForDevice(selectedDeviceCode.value || 'uav-01')
  void visualSensorStore.selectFor('MISSION_CENTER', focusedCameraId)
  unityBridgeStore.sendFor('MISSION_CENTER', 'visualSensorSubscribe', {
    enabled,
    missionId: context.missionId,
    runId: context.runId,
    runtimeInstanceId: context.runtimeInstanceId,
    focusedCameraId,
    displayMode,
    quality: '720p',
    targetFps: 30,
    gpuDirect: true,
    jpegFallback: false,
    thumbnailFps: 0.2,
    focusedFps: 1,
  })
}

function clearRunFrames() {
  algorithmFrame.value = null
  loadedScenarioKey = ''
  trajectoryStore.clearFor('MISSION_CENTER')
  unityBridgeStore.clearPoseFramesFor('MISSION_CENTER')
}

async function ensureAlgorithmRuntime() {
  if (!detail.value?.currentRun || !['GB_SFLA_CS', 'ESCORT_GUARD'].includes(activeAlgorithmCode.value)) return
  if (algorithmRecoveryPromise) return algorithmRecoveryPromise
  algorithmRecoveryPromise = (async () => {
    const active = detail.value!.currentRun!
    const runtime = await prepareAlgorithmRun(
      active.id,
      activeAlgorithmCode.value,
      currentAlgorithmConfig(),
    )
    if (activeMission.value?.status === 'RUNNING' && runtime.state !== 'RUNNING') {
      await controlAlgorithmRun(active.id, 'start')
    }
  })()
  try {
    await algorithmRecoveryPromise
  } finally {
    algorithmRecoveryPromise = null
  }
}

function sendAlgorithmPoseFrame(frame: AlgorithmRuntimeFrame) {
  unityBridgeStore.sendFor('MISSION_CENTER', 'poseFrame', {
    algorithmCode: frame.algorithmCode,
    runId: frame.runId,
    sequence: frame.sequence,
    timestamp: frame.timestamp,
    phase: frame.phase,
    agents: frame.agents,
    targets: frame.targets,
    route: frame.route.map(point => ({ x: point[0], y: point[1] })),
    obstacles: frame.obstacles,
  })
}

function ensureMissionScenarioLoaded() {
  if (!unityChannel.value.controlsReady) {
    loadedScenarioKey = ''
    return
  }
  const mission = activeMission.value
  const run = detail.value?.currentRun
  if (!mission || !run || !['GB_SFLA_CS', 'ESCORT_GUARD'].includes(mission.algorithmCode)) return
  const key = `${mission.id}:${run.id}:${mission.algorithmCode}:${unityViewportStore.missionInstanceId}`
  if (loadedScenarioKey === key) return
  unityBridgeStore.clearPoseFramesFor('MISSION_CENTER')
  unityBridgeStore.sendFor('MISSION_CENTER', 'loadScenario', {
    algorithmCode: mission.algorithmCode,
    missionId: mission.id,
    runId: run.id,
  })
  if (algorithmFrame.value?.runId === run.id) sendAlgorithmPoseFrame(algorithmFrame.value)
  loadedScenarioKey = key
}

function ingestAlgorithmFrame(frame: AlgorithmRuntimeFrame) {
  if (frame.runId !== currentRunId.value) return
  if (algorithmFrame.value && frame.sequence <= algorithmFrame.value.sequence) return
  algorithmFrame.value = frame
  const agents = [
    ...frame.agents.map(item => ({
      code: item.code,
      type: item.type,
      x: item.x,
      y: item.y,
      z: item.z,
      yaw: item.heading,
      state: item.role,
    })),
    ...frame.targets
      .filter(item => item.visible !== false)
      .map(item => ({
        code: item.code,
        type: 'TARGET',
        x: item.x,
        y: item.y,
        z: item.z,
        yaw: item.heading,
        state: item.type,
      })),
  ]
  trajectoryStore.ingestFor('MISSION_CENTER', {
    sequence: frame.sequence,
    timestamp: frame.timestamp,
    source: `algorithm:${frame.algorithmCode}`,
    coordinateSystem: 'MISSION_SCENE_XZ',
    mission: {
      phase: frame.phase,
      elapsed: Math.round(frame.sequence / 10),
      captureRadius: Number(frame.metrics.usvFormationRadius ?? frame.metrics.captureRadius ?? 16),
      defenseRadius: Number(
        frame.metrics.escortFormationRadius ?? frame.metrics.uavFormationRadius ?? 18,
      ),
      captureReady: frame.metrics.captured === true,
      formationHolding: frame.phase === 'CAPTURED' || frame.phase === 'THREAT_RESPONSE',
    },
    agents,
  })
  sendAlgorithmPoseFrame(frame)
}

async function pollAlgorithmFrames() {
  if (!currentRunId.value || algorithmPolling.value) return
  algorithmPolling.value = true
  algorithmAbortController = new AbortController()
  try {
    const frames = await fetchAlgorithmFrames(
      currentRunId.value,
      algorithmFrame.value?.sequence ?? 0,
      algorithmAbortController.signal,
    )
    frames.forEach(ingestAlgorithmFrame)
  } catch {
    // 短暂轮询失败不应终止 RUN，也不在页面连续弹出错误。
  } finally {
    algorithmAbortController = null
    algorithmPolling.value = false
  }
}

function stopAlgorithmPolling() {
  if (algorithmPollTimer !== null) window.clearInterval(algorithmPollTimer)
  algorithmPollTimer = null
  algorithmAbortController?.abort()
  algorithmAbortController = null
}

function startAlgorithmPolling(forceRunning = false) {
  stopAlgorithmPolling()
  if (!currentRunId.value) return
  void pollAlgorithmFrames()
  if (!forceRunning && activeMission.value?.status !== 'RUNNING') return
  algorithmPollTimer = window.setInterval(() => void pollAlgorithmFrames(), 100)
}

async function loadMissionWorkspace(mission: Mission, requestedRunId?: number | null) {
  stopAlgorithmPolling()
  const loaded = await fetchMission(mission.id)
  if (requestedRunId) {
    const requested = loaded.runs.find(run => run.id === requestedRunId)
    if (requested) loaded.currentRun = requested
  }
  if (loaded.currentRun?.id !== currentRunId.value) clearRunFrames()
  detail.value = loaded
  selectedAlgorithmCode.value = loaded.mission.algorithmCode
  sessionStore.bind(loaded.mission.id, loaded.currentRun?.id ?? null)
  unityViewportStore.prepareMission(
    loaded.mission.id,
    loaded.currentRun?.id ?? null,
    loaded.currentRun?.runtimeInstanceId,
  )
  visualSensorStore.bindRuntime(missionVisualContext())
  if (activeRun.value) {
    await ensureAlgorithmRuntime()
    startAlgorithmPolling()
  } else if (loaded.currentRun) {
    startAlgorithmPolling()
  }
  ensureMissionScenarioLoaded()
}

async function loadAlgorithmMission(code: string) {
  const mission = missionForAlgorithm(code)
  if (!mission) throw new Error('未找到该算法对应的任务模板，请先检查数据库任务配置')
  await loadMissionWorkspace(mission)
}

async function refreshWorkspace() {
  loading.value = true
  try {
    const [algorithmList] = await Promise.all([
      fetchAlgorithms(),
      missionStore.refresh({ page: 0, size: 100 }),
      monitoringStore.refresh({}, true),
    ])
    algorithms.value = algorithmList
    const queryMissionId = queryNumber(route.query.missionId)
    const queryRunId = queryNumber(route.query.runId)
    const routedMission = queryMissionId
      ? missionStore.records.find(item => item.id === queryMissionId)
      : null
    const openMission = missionStore.records.find(item => ['RUNNING', 'PAUSED'].includes(item.status))
    const preferredAlgorithm = algorithms.value.find(
      item => item.enabled && item.code === 'GB_SFLA_CS',
    ) ?? enabledAlgorithms.value[0]
    const mission = routedMission
      ?? openMission
      ?? missionForAlgorithm(preferredAlgorithm?.code ?? 'GB_SFLA_CS')
      ?? missionStore.records[0]
    if (!mission) throw new Error('任务中心没有可执行任务模板')
    await loadMissionWorkspace(mission, queryRunId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务中心加载失败')
  } finally {
    loading.value = false
  }
}

async function waitForMissionUnity(timeoutMs = 20_000) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    if (unityChannel.value.connected && unityChannel.value.controlsReady) return
    await new Promise(resolve => window.setTimeout(resolve, 250))
  }
  throw new Error('任务中心 Unity WebGL 指令桥尚未就绪，请稍后重试')
}

async function applyMissionAction(
  action: 'pause' | 'resume' | 'complete' | 'cancel',
  confirmCancel = true,
) {
  if (!detail.value) return false
  if (action === 'cancel' && confirmCancel) {
    try {
      await ElMessageBox.confirm(
        '确认终止当前任务运行？该操作只影响任务中心，不影响系统总览。',
        '终止任务',
        { type: 'warning', confirmButtonText: '确认终止', cancelButtonText: '取消' },
      )
    } catch {
      return false
    }
  }
  busy.value = true
  try {
    const missionId = detail.value.mission.id
    const runId = currentRunId.value
    if (!unityChannel.value.connected || !unityChannel.value.controlsReady) {
      throw new Error('任务中心 Unity 指令桥尚未就绪')
    }
    const result = await executeMissionAction(
      missionId,
      action,
      'MISSION_CONTROL',
      unityViewportStore.missionInstanceId,
    )
    if (result.command) {
      if (['FAILED', 'TIMEOUT'].includes(result.command.status)) {
        throw new Error(result.command.detail || '任务指令创建失败')
      }
      const ack = await unityBridgeStore.sendControlCommandAndWaitFor(
        'MISSION_CENTER',
        missionUnityCommand(action),
        '',
        result.command.commandKey,
      )
      if (!ack.success) throw new Error(ack.status || 'Unity 未确认任务指令')
    }
    if (runId) {
      try {
        if (action === 'pause') await controlAlgorithmRun(runId, 'pause')
        if (action === 'resume') {
          await ensureAlgorithmRuntime()
          await controlAlgorithmRun(runId, 'resume')
        }
        if (action === 'complete') await controlAlgorithmRun(runId, 'stop')
        if (action === 'cancel') await controlAlgorithmRun(runId, 'cancel')
      } catch (error) {
        ElMessage.warning(error instanceof Error ? error.message : '算法运行实例未响应')
      }
    }
    detail.value = result.detail
    if (action === 'pause') {
      sessionStore.pause()
      stopAlgorithmPolling()
    } else if (action === 'resume') {
      sessionStore.resume(trajectoryFrame.value?.sequence ?? 0)
      startAlgorithmPolling(true)
    } else {
      sessionStore.stop()
      stopAlgorithmPolling()
    }
    ElMessage.success(
      action === 'pause'
        ? '任务已暂停'
        : action === 'resume'
          ? '任务已继续'
          : action === 'complete'
            ? '任务已完成'
            : '任务已终止',
    )
    return true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务指令执行失败')
    return false
  } finally {
    busy.value = false
  }
}

async function startSelectedAlgorithm() {
  if (busy.value) return
  const switching = activeRun.value
  if (switching) {
    try {
      const targetName = currentAlgorithm.value?.name ?? selectedAlgorithmCode.value
      await ElMessageBox.confirm(
        `将终止当前 RUN、重置轨迹与 Unity 场景，然后执行“${targetName}”。是否继续？`,
        selectedAlgorithmCode.value === activeAlgorithmCode.value ? '重新执行任务' : '切换算法',
        { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  busy.value = true
  let preparedRunId: number | null = null
  try {
    if (switching && !await applyMissionAction('cancel', false)) return
    if (!detail.value || detail.value.mission.algorithmCode !== selectedAlgorithmCode.value) {
      await loadAlgorithmMission(selectedAlgorithmCode.value)
    }
    if (!detail.value) throw new Error('未找到可执行任务')
    let working = detail.value
    if (working.mission.status !== 'READY') {
      const ready = await executeMissionAction(
        working.mission.id,
        'ready',
        'MISSION_CONTROL',
        unityViewportStore.missionInstanceId,
      )
      working = ready.detail
      detail.value = working
    }
    unityViewportStore.createMissionInstance(working.mission.id)
    unityViewportStore.prepareMission(working.mission.id, null)
    await waitForMissionUnity()
    const preflight = await fetchMissionPreflight(
      working.mission.id,
      unityViewportStore.missionInstanceId,
    )
    if (!preflight.canStart) {
      throw new Error(preflight.issues.map(issue => issue.message).join('；') || '任务启动检查未通过')
    }
    const result = await executeMissionAction(
      working.mission.id,
      'start',
      'MISSION_CONTROL',
      unityViewportStore.missionInstanceId,
    )
    detail.value = result.detail
    const run = result.detail.currentRun
    if (!run) throw new Error('后端未创建任务 RUN')
    preparedRunId = run.id
    clearRunFrames()
    unityViewportStore.prepareMission(working.mission.id, run.id, run.runtimeInstanceId)
    await prepareAlgorithmRun(run.id, selectedAlgorithmCode.value, currentAlgorithmConfig())
    unityBridgeStore.sendFor('MISSION_CENTER', 'loadScenario', {
      algorithmCode: selectedAlgorithmCode.value,
      missionId: working.mission.id,
      runId: run.id,
    })
    if (result.command) {
      if (['FAILED', 'TIMEOUT'].includes(result.command.status)) {
        throw new Error(result.command.detail || '任务启动指令创建失败')
      }
      const ack = await unityBridgeStore.sendControlCommandAndWaitFor(
        'MISSION_CENTER',
        'missionStart',
        '',
        result.command.commandKey,
      )
      if (!ack.success) throw new Error(ack.status || 'Unity 未确认任务启动')
    }
    await controlAlgorithmRun(run.id, 'start')
    detail.value = await fetchMission(working.mission.id)
    sessionStore.bind(working.mission.id, run.id)
    sessionStore.start(trajectoryFrame.value?.sequence ?? 0, run.id)
    startAlgorithmPolling(true)
    ensureMissionScenarioLoaded()
    ElMessage.success(`${currentAlgorithm.value?.name ?? '算法'}已开始执行`)
  } catch (error) {
    if (preparedRunId) void controlAlgorithmRun(preparedRunId, 'cancel').catch(() => undefined)
    ElMessage.error(error instanceof Error ? error.message : '算法执行失败')
  } finally {
    busy.value = false
  }
}

async function onAlgorithmSelected(code: string) {
  selectedAlgorithmCode.value = code
  if (activeRun.value) return
  try {
    await loadAlgorithmMission(code)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '算法任务加载失败')
  }
}

function selectObservationDevice(deviceCode: string) {
  selectedDeviceCode.value = deviceCode
  if (!deviceCode) {
    if (mode.value === 'vision') {
      visualDisplayMode.value = 'grid'
      sendMissionVisualSubscription(true, 'grid')
    } else if (mode.value === '3d') {
      unityBridgeStore.sendFor('MISSION_CENTER', 'switchCamera', { mode: 'overview' })
    }
    return
  }
  if (mode.value === 'vision') {
    visualDisplayMode.value = 'focus'
    sendMissionVisualSubscription(true, 'focus')
  } else if (mode.value === '3d') {
    unityBridgeStore.sendFor('MISSION_CENTER', 'selectDevice', { deviceCode })
    unityBridgeStore.sendFor('MISSION_CENTER', 'switchCamera', { mode: 'device-follow' })
  }
}

function changeMode(next: WorkspaceMode) {
  const leavingVision = mode.value === 'vision' && next !== 'vision'
  stopRadarPolling()
  mode.value = next
  void router.replace({ query: next === '2d' ? {} : { view: next } })
  if (leavingVision) sendMissionVisualSubscription(false, 'off')
  if (next === '2d' || next === 'radar') {
    unityViewportStore.park()
    if (next === 'radar') startRadarPolling()
    return
  }
  if (next === 'vision' && !currentRunId.value) {
    unityViewportStore.park()
    return
  }
  unityViewportStore.show('mission-execution')
  if (next === 'vision') {
    visualDisplayMode.value = selectedDeviceCode.value ? 'focus' : 'grid'
    sendMissionVisualSubscription(true, visualDisplayMode.value)
  }
}

async function placeThreat(x: number, y: number) {
  if (activeAlgorithmCode.value !== 'ESCORT_GUARD' || !currentRunId.value) return
  try {
    await placeEscortThreat(currentRunId.value, x, y)
    ElMessage.success(`威胁目标已更新：${x.toFixed(1)}, ${y.toFixed(1)}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '威胁目标更新失败')
  }
}

async function toggleAlgorithm(algorithm: AlgorithmDefinition, enabled: boolean) {
  algorithmBusy.value = true
  try {
    await setAlgorithmEnabled(algorithm.code, enabled)
    algorithms.value = await fetchAlgorithms()
    ElMessage.success(enabled ? '算法已启用' : '算法已停用')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '算法状态更新失败')
  } finally {
    algorithmBusy.value = false
  }
}

async function makeDefaultAlgorithm(algorithm: AlgorithmDefinition) {
  algorithmBusy.value = true
  try {
    await setDefaultAlgorithm(algorithm.code)
    algorithms.value = await fetchAlgorithms()
    ElMessage.success('默认算法已更新')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '默认算法更新失败')
  } finally {
    algorithmBusy.value = false
  }
}

watch(
  [
    () => unityChannel.value.controlsReady,
    activeAlgorithmCode,
    currentRunId,
    () => unityViewportStore.missionInstanceId,
  ],
  ensureMissionScenarioLoaded,
  { immediate: true },
)

watch(trajectoryFrame, frame => {
  if (!frame || selectedDeviceCode.value) return
  const firstVehicle = frame.agents.find(agent => agent.type === 'UAV' || agent.type === 'USV')
  if (!firstVehicle) return
}, { immediate: true })

onMounted(async () => {
  unityViewportStore.park()
  monitoringStore.connectEvents()
  mode.value = requestedViewMode()
  await refreshWorkspace()
  changeMode(mode.value)
})

let resumeAfterDeactivation = false

onActivated(() => {
  if (!resumeAfterDeactivation) return
  resumeAfterDeactivation = false
  monitoringStore.connectEvents()
  if (activeRun.value || currentRunId.value) startAlgorithmPolling()
  visualSensorStore.bindRuntime(missionVisualContext())
  changeMode(mode.value)
})

onDeactivated(() => {
  resumeAfterDeactivation = true
  stopAlgorithmPolling()
  stopRadarPolling()
  if (mode.value === 'vision') sendMissionVisualSubscription(false, 'off')
  visualSensorStore.disposeFrames('MISSION_CENTER')
  unityViewportStore.park()
})

onBeforeUnmount(() => {
  stopAlgorithmPolling()
  stopRadarPolling()
  if (mode.value === 'vision') sendMissionVisualSubscription(false, 'off')
  visualSensorStore.disposeFrames('MISSION_CENTER')
  unityViewportStore.park()
})
</script>

<template>
  <ConsoleLayout title="任务中心" eyebrow="MISSION CENTER" :show-refresh="false">
    <template #actions>
      <div class="mission-health">
        <span><i :class="{ online: rosOnline }" />ROS {{ rosOnline ? '在线' : '离线' }}</span>
        <span><i :class="{ online: unityChannel.connected }" />Unity {{ unityChannel.connected ? '就绪' : '连接中' }}</span>
        <span><i :class="{ online: onlineVehicleCount >= 6 }" />设备 {{ onlineVehicleCount }}/6</span>
      </div>
    </template>

    <section class="mission-workspace" :aria-busy="loading">
      <header class="algorithm-toolbar">
        <div class="algorithm-picker">
          <label for="mission-algorithm">当前算法</label>
          <el-select
            id="mission-algorithm"
            :model-value="selectedAlgorithmCode"
            :disabled="busy"
            @change="onAlgorithmSelected"
          >
            <el-option
              v-for="algorithm in enabledAlgorithms"
              :key="algorithm.code"
              :label="`${algorithm.name} v${algorithm.version}`"
              :value="algorithm.code"
            />
          </el-select>
          <button type="button" class="secondary-button" @click="algorithmManagerVisible=true">
            <Settings2 :size="15" />算法管理
          </button>
        </div>
        <div class="algorithm-summary">
          <span>{{ sceneScale }}</span>
          <em :class="activeMission?.status.toLowerCase()">{{ statusLabel }}</em>
        </div>
        <button class="primary-button" type="button" :disabled="busy || !currentAlgorithm" @click="startSelectedAlgorithm">
          <Play :size="17" />{{ primaryActionLabel }}
        </button>
      </header>

      <section class="execution-card">
        <header class="run-toolbar">
          <div class="mission-identity">
            <small>{{ activeMission?.code ?? 'MISSION' }} · RUN {{ detail?.currentRun?.runNo ?? '--' }}</small>
            <strong>{{ activeMission?.name ?? '任务中心运行工作台' }}</strong>
          </div>
          <nav class="mode-switch" aria-label="任务视图">
            <button :class="{ active: mode === '2d' }" @click="changeMode('2d')"><Layers3 :size="16" />2D 轨迹</button>
            <button :class="{ active: mode === '3d' }" @click="changeMode('3d')"><Box :size="16" />3D Unity</button>
            <button :class="{ active: mode === 'vision' }" @click="changeMode('vision')"><Camera :size="16" />设备视觉</button>
            <button :class="{ active: mode === 'radar' }" @click="changeMode('radar')"><Radio :size="16" />雷达感知</button>
          </nav>
          <span class="run-sync"><i />{{ runSyncText }}</span>
          <div class="run-actions">
            <button
              :disabled="busy || !activeRun"
              @click="applyMissionAction(activeMission?.status === 'PAUSED' ? 'resume' : 'pause')"
            >
              <Play v-if="activeMission?.status === 'PAUSED'" :size="15" />
              <Pause v-else :size="15" />
              {{ activeMission?.status === 'PAUSED' ? '继续' : '暂停' }}
            </button>
            <button :disabled="busy || !activeRun" @click="applyMissionAction('complete')">
              <Square :size="15" />完成
            </button>
            <button class="danger" :disabled="busy || !activeRun" @click="applyMissionAction('cancel')">
              <XOctagon :size="15" />终止
            </button>
          </div>
        </header>

        <main class="execution-stage">
          <AlgorithmTrajectoryMap
            v-if="mode === '2d' && algorithmFrame"
            :frame="algorithmFrame"
            :mission-name="activeMission?.name ?? '算法轨迹'"
            :selected-device-code="selectedDeviceCode"
            @select="selectObservationDevice"
            @place-threat="placeThreat"
          />
          <MissionTrajectoryMap
            v-else-if="mode === '2d'"
            :mission-name="activeMission?.name ?? '任务轨迹'"
            :mission-status="activeMission?.status ?? 'READY'"
            :selected-device-code="selectedDeviceCode"
            :trajectory-frame="trajectoryFrame"
            :session-state="sessionStore.state"
            :session-revision="sessionStore.revision"
            @select-device="selectObservationDevice"
          />
          <div
            v-else-if="mode === '3d'"
            class="unity-viewport"
            data-unity-runtime-viewport="mission-execution"
          >
            <span class="unity-badge"><i />UNITY WEBGL ONLINE</span>
          </div>
          <section v-else-if="mode === 'radar'" class="radar-panel">
            <header>
              <span>RADAR PERCEPTION</span>
              <strong>Radar / pointcloud summary</strong>
              <i :class="{ online: radarOverview.connected }" />
            </header>
            <div class="radar-metrics">
              <article><span>Online</span><strong>{{ radarOverview.onlineCount }}/{{ radarOverview.totalCount || '--' }}</strong></article>
              <article><span>Nearest obstacle</span><strong>{{ formatRadarRange(radarOverview.nearestObstacleRange) }}</strong></article>
              <article><span>Points</span><strong>{{ radarOverview.detectionCount }}</strong></article>
              <article><span>Latest target</span><strong>{{ radarOverview.latestTargetId || '--' }}</strong></article>
            </div>
            <div class="radar-plot" aria-label="2D pointcloud overview">
              <svg viewBox="0 0 100 100" role="img">
                <circle class="plot-ring" cx="50" cy="50" r="44" />
                <circle class="plot-ring muted" cx="50" cy="50" r="29" />
                <circle class="plot-ring muted" cx="50" cy="50" r="14" />
                <line class="plot-axis" x1="50" y1="6" x2="50" y2="94" />
                <line class="plot-axis" x1="6" y1="50" x2="94" y2="50" />
                <circle class="plot-origin" cx="50" cy="50" r="2.4" />
                <circle
                  v-for="point in radarPlotPoints"
                  :key="point.id"
                  class="plot-point"
                  :cx="point.cx"
                  :cy="point.cy"
                  r="1.35"
                >
                  <title>{{ point.id }} {{ formatRadarRange(point.range) }}</title>
                </circle>
              </svg>
              <div v-if="radarPlotPoints.length === 0" class="radar-plot-empty">Waiting for pointcloud_frame</div>
            </div>
            <div class="radar-table">
              <div class="radar-row head"><span>ID</span><span>Type</span><span>Range</span><span>Time</span></div>
              <div v-for="item in radarItems" :key="`${item.deviceId}-${item.kind}-${item.id}`" class="radar-row">
                <span>{{ item.id }}</span>
                <span>{{ item.kind }}</span>
                <span>{{ formatRadarRange(item.range) }}</span>
                <span>{{ formatRadarTime(item.timestampMs) }}</span>
              </div>
              <div v-if="radarItems.length === 0" class="radar-empty">Waiting for radar_frame / pointcloud_frame</div>
            </div>
          </section>
          <div
            v-else-if="currentRunId"
            class="unity-viewport vision"
            data-unity-runtime-viewport="mission-execution"
          >
            <span class="unity-badge"><i />六路视觉 {{ missionVisualConnected ? 'LIVE' : 'CONNECTING' }}</span>
          </div>
          <div v-else class="visual-waiting">
            <Camera :size="38" />
            <strong>设备视觉等待任务 RUN</strong>
            <span>选择算法并开始任务后，可在此查看六路 Unity 设备视觉。</span>
          </div>
        </main>
      </section>

      <footer class="event-dock">
        <div class="readiness">
          <span><CircleCheck :size="15" />ROS {{ rosOnline ? '已连接' : '等待连接' }}</span>
          <span><CircleCheck :size="15" />Unity {{ unityChannel.connected ? '已就绪' : '初始化中' }}</span>
          <span><Radio :size="15" />设备 {{ onlineVehicleCount }}/6 在线</span>
        </div>
        <div class="event-list">
          <article v-for="event in recentEvents" :key="event.id">
            <Clock3 :size="14" />
            <span><time>{{ new Date(event.occurredAt).toLocaleTimeString() }}</time><b>{{ event.title }}</b></span>
          </article>
        </div>
        <button type="button" @click="eventVisible=true">查看全部事件</button>
      </footer>
    </section>

    <AlgorithmManagerDialog
      v-model="algorithmManagerVisible"
      :algorithms="algorithms"
      :loading="algorithmBusy"
      @toggle="toggleAlgorithm"
      @set-default="makeDefaultAlgorithm"
    />
    <MissionEventDrawer
      v-model="eventVisible"
      :mission-id="detail?.mission.id ?? null"
      :run-id="currentRunId ?? undefined"
    />
  </ConsoleLayout>
</template>

<style scoped>
.mission-workspace {
  display: grid;
  grid-template-rows: auto minmax(clamp(560px, calc(100dvh - 300px), 900px), 1fr) auto;
  gap: 10px;
  width: 100%;
  max-width: 2360px;
  min-height: calc(100dvh - 106px);
  margin: 0 auto;
  color: #dff5f3;
}

.mission-health,
.algorithm-picker,
.algorithm-summary,
.mode-switch,
.run-actions,
.readiness,
.event-list {
  display: flex;
  align-items: center;
}

.mission-health {
  gap: 9px;
}

.mission-health span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  color: #92b0b3;
  border: 1px solid rgba(77, 176, 194, .16);
  border-radius: 5px;
  background: rgba(7, 31, 41, .72);
  font-size: 10px;
}

.mission-health i,
.run-sync i,
.unity-badge i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64797c;
}

.mission-health i.online,
.run-sync i,
.unity-badge i {
  background: #55e7a7;
  box-shadow: 0 0 7px rgba(85, 231, 167, .8);
}

.algorithm-toolbar,
.execution-card,
.event-dock {
  border: 1px solid rgba(76, 180, 202, .22);
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(5, 27, 37, .97), rgba(3, 17, 25, .97));
}

.algorithm-toolbar {
  display: grid;
  grid-template-columns: minmax(450px, 1.25fr) minmax(280px, .75fr) 150px;
  align-items: center;
  gap: 14px;
  min-height: 66px;
  padding: 10px 14px;
}

.algorithm-picker {
  gap: 9px;
}

.algorithm-picker label {
  flex: 0 0 auto;
  color: #8db0b4;
  font-size: 11px;
  font-weight: 700;
}

.algorithm-picker :deep(.el-select) {
  width: min(390px, 48vw);
}

.algorithm-picker :deep(.el-select__wrapper) {
  min-height: 38px;
  color: #e7f7f6;
  background: #061b24;
  box-shadow: 0 0 0 1px #2a5660 inset;
}

.secondary-button,
.primary-button,
.run-actions button,
.mode-switch button,
.event-dock > button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #d5ecea;
  border: 1px solid #2a5660;
  border-radius: 5px;
  background: #08232d;
  cursor: pointer;
}

.secondary-button {
  flex: 0 0 auto;
  height: 38px;
  padding: 0 12px;
}

.algorithm-summary {
  justify-content: flex-end;
  gap: 12px;
  color: #cfe4e3;
  font-size: 11px;
}

.algorithm-summary em {
  padding: 5px 9px;
  color: #ffc93e;
  border: 1px solid rgba(255, 201, 62, .38);
  border-radius: 4px;
  background: rgba(255, 201, 62, .07);
  font-style: normal;
}

.algorithm-summary em.running,
.algorithm-summary em.paused {
  color: #55e7a7;
  border-color: rgba(85, 231, 167, .35);
  background: rgba(85, 231, 167, .07);
}

.algorithm-summary em.failed,
.algorithm-summary em.cancelled {
  color: #ff7474;
  border-color: rgba(255, 116, 116, .35);
}

.primary-button {
  height: 42px;
  color: #02232a;
  border-color: #63e6e2;
  background: linear-gradient(135deg, #53e1df, #29bed1);
  font-weight: 900;
}

button:disabled {
  cursor: not-allowed;
  opacity: .42;
}

.execution-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.run-toolbar {
  display: grid;
  grid-template-columns: minmax(220px, .8fr) auto minmax(170px, .55fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(70, 164, 183, .18);
}

.mission-identity small,
.mission-identity strong {
  display: block;
}

.mission-identity small {
  color: #4bd2e5;
  font-size: 9px;
  letter-spacing: .04em;
}

.mission-identity strong {
  margin-top: 3px;
  overflow: hidden;
  color: #efffff;
  font-size: 14px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.mode-switch {
  justify-content: center;
}

.mode-switch button {
  min-width: 126px;
  height: 36px;
  border-radius: 0;
}

.mode-switch button:first-child {
  border-radius: 5px 0 0 5px;
}

.mode-switch button:last-child {
  border-radius: 0 5px 5px 0;
}

.mode-switch button.active {
  color: #56e2df;
  border-color: #53dce0;
  background: #0a3540;
}

.run-sync {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  color: #55e7a7;
  font-size: 9px;
}

.run-actions {
  justify-content: flex-end;
  gap: 6px;
}

.run-actions button {
  min-height: 34px;
  padding: 0 10px;
}

.run-actions button.danger {
  color: #ff7474;
  border-color: #8c3940;
}

.execution-stage {
  position: relative;
  min-height: clamp(500px, calc(100dvh - 380px), 820px);
  overflow: hidden;
  background: #020f16;
}

.execution-stage :deep(.algorithm-map),
.execution-stage :deep(.mission-trajectory-map) {
  width: 100%;
  height: 100%;
}

.unity-viewport {
  position: absolute;
  inset: 0;
  background: #03131b;
}

.unity-viewport.vision {
  background: #02090d;
}

.unity-badge {
  position: absolute;
  z-index: 2;
  top: 12px;
  right: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  color: #d8f1ee;
  border: 1px solid rgba(92, 201, 202, .35);
  border-radius: 4px;
  background: rgba(2, 20, 28, .86);
  font-size: 9px;
  font-weight: 800;
}

.radar-panel {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  box-sizing: border-box;
  height: auto;
  padding: 12px;
  overflow: hidden;
  border: 1px solid rgba(76, 185, 197, .24);
  border-radius: 8px;
  background: rgba(5, 24, 31, .82);
}

.radar-panel header,
.radar-metrics,
.radar-row {
  display: grid;
  align-items: center;
}

.radar-panel header {
  grid-template-columns: 1fr auto 9px;
  gap: 12px;
  margin-bottom: 10px;
}

.radar-panel header span {
  color: #4cd6e9;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .13em;
}

.radar-panel header strong {
  color: #dff9f5;
  font-size: 13px;
}

.radar-panel header i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #607b7e;
}

.radar-panel header i.online {
  background: #5ce7b7;
  box-shadow: 0 0 9px rgba(92, 231, 183, .75);
}

.radar-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.radar-metrics article {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  background: #071a21;
}

.radar-metrics span,
.radar-row span {
  color: #769a9b;
  font-size: 10px;
}

.radar-metrics strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #e7fffb;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.radar-plot {
  position: relative;
  min-height: 0;
  margin-bottom: 10px;
  overflow: hidden;
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  background: linear-gradient(rgba(73, 160, 170, .07) 1px, transparent 1px), linear-gradient(90deg, rgba(73, 160, 170, .06) 1px, transparent 1px), #04161d;
  background-size: 24px 24px;
}

.radar-plot svg {
  width: 100%;
  height: 100%;
}

.plot-ring,
.plot-axis {
  fill: none;
  stroke: rgba(117, 203, 205, .22);
  stroke-width: .5;
}

.plot-ring.muted { stroke: rgba(117, 203, 205, .12); }
.plot-origin { fill: #65ddcf; filter: drop-shadow(0 0 5px rgba(101, 221, 207, .8)); }
.plot-point { fill: #5ce7b7; opacity: .82; }

.radar-plot-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #628487;
  font-size: 11px;
}

.radar-table {
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  overflow: hidden;
}

.radar-row {
  grid-template-columns: 1.2fr 1fr 1fr 1fr;
  min-height: 32px;
  border-bottom: 1px solid rgba(72, 145, 155, .13);
}

.radar-row:last-child { border-bottom: 0; }

.radar-row span {
  min-width: 0;
  padding: 0 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.radar-row.head { background: rgba(76, 185, 197, .08); }
.radar-row.head span { color: #9ec3c3; font-weight: 900; }

.radar-empty {
  padding: 18px;
  color: #628487;
  font-size: 11px;
  text-align: center;
}

.visual-waiting {
  display: grid;
  height: 100%;
  place-content: center;
  justify-items: center;
  gap: 9px;
  color: #6f9599;
  background:
    radial-gradient(circle at center, rgba(37, 132, 150, .1), transparent 42%),
    #020f16;
}

.visual-waiting strong {
  color: #cfe5e3;
  font-size: 16px;
}

.visual-waiting span {
  font-size: 11px;
}

.event-dock {
  display: grid;
  grid-template-columns: auto minmax(320px, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 70px;
  padding: 9px 12px;
}

.readiness {
  gap: 14px;
}

.readiness span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #82a5a8;
  font-size: 9px;
}

.readiness svg {
  color: #55e7a7;
}

.event-list {
  min-width: 0;
  gap: 7px;
}

.event-list article {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 7px;
  padding: 7px 9px;
  border: 1px solid rgba(72, 155, 172, .13);
  border-radius: 5px;
  background: rgba(7, 31, 41, .56);
}

.event-list article svg {
  flex: 0 0 auto;
  color: #4dcfe3;
}

.event-list time,
.event-list b {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.event-list time {
  color: #5f858a;
  font-size: 8px;
}

.event-list b {
  max-width: 180px;
  color: #cfe4e2;
  font-size: 9px;
}

.event-dock > button {
  height: 34px;
  padding: 0 12px;
  color: #54dce0;
}

@media (max-width: 1280px) {
  .algorithm-toolbar {
    grid-template-columns: minmax(390px, 1fr) auto 135px;
  }

  .run-toolbar {
    grid-template-columns: minmax(190px, 1fr) auto auto;
  }

  .run-sync {
    display: none;
  }

  .mode-switch button {
    min-width: 104px;
  }

  .event-dock {
    grid-template-columns: 1fr auto;
  }

  .event-list {
    display: none;
  }
}

@media (max-width: 920px) {
  .algorithm-toolbar {
    grid-template-columns: 1fr auto;
  }

  .algorithm-summary {
    display: none;
  }

  .run-toolbar {
    grid-template-columns: 1fr;
  }

  .mode-switch,
  .run-actions {
    justify-content: flex-start;
  }

}

@media (min-width: 1920px) {
  .mission-workspace {
    gap: 12px;
  }

  .algorithm-toolbar {
    grid-template-columns: minmax(520px, 1.3fr) minmax(320px, .7fr) 168px;
    padding-inline: 18px;
  }

  .run-toolbar {
    padding-inline: 16px;
  }

  .mode-switch button {
    min-width: 142px;
  }
}

@media (min-width: 1920px) and (min-height: 1000px) {
  .mission-workspace {
    grid-template-rows: auto minmax(700px, 1fr) auto;
  }

  .execution-stage {
    min-height: clamp(660px, calc(100dvh - 360px), 900px);
  }
}
</style>
