<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import {
  Camera,
  CheckCircle2,
  CircleStop,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RefreshCw,
  Send,
  SquareStack,
} from '@lucide/vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'
import {
  controlAlgorithmRun,
  fetchAlgorithmFrames,
  prepareAlgorithmRun,
} from '@/api/algorithm'
import type { AlgorithmRuntimeFrame } from '@/types/mission'
import {
  adaptVirtualAlgorithmFrame,
  type EnuOrigin,
  type VirtualPoseStateMap,
} from '@/utils/virtualAlgorithmFrameAdapter'
import {
  buildVirtualFleetGridLayout,
  type GridScenarioPose,
} from '@/utils/virtualFleetGridLayout'
import { deriveAdaptiveScenarioPlan } from '@/utils/adaptiveScenarioPlan'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

type ScenarioInitialPose = {
  deviceCode: string
  deviceType?: string
  eastM: number
  northM: number
  upM: number
  headingDeg: number
  speedMps?: number
  state?: string
  valid?: boolean
}

type CaptureGroupMetric = {
  threatCode?: string
  state?: string
  stage?: number
  memberCount?: number
  uavCount?: number
  usvCount?: number
  arrivalRatio?: number
  holdFrames?: number
  holdRequiredFrames?: number
  pursuitDistanceM?: number
  requiredPursuitDistanceM?: number
  intent?: string
  triggerReason?: string
}

const unityPanel = ref<InstanceType<typeof UnityWebglPanel> | null>(null)
const unityReady = ref(false)
const lastMessage = ref<UnityMessage | null>(null)
const selectedDevice = ref('')
const cameraMode = ref('overview')
const logs = ref<string[]>([])
const scenarioReadyRunId = ref<number | null>(null)
const scenarioLoading = ref(false)
const algorithmPrepared = ref(false)
const algorithmPreparing = ref(false)
const missionActionMessage = ref('')
const webglExpanded = ref(false)
const currentAlgorithmFrame = ref<AlgorithmRuntimeFrame | null>(null)
const initialScenarioPoses = ref<ScenarioInitialPose[]>([])
const plannedScenarioPoses = ref<GridScenarioPose[]>([])
const sceneLocked = computed(() => state.mission === 'RUNNING' || state.mission === 'PAUSED')
const scenarioPlan = computed(() => deriveAdaptiveScenarioPlan(state.uavCount, state.usvCount))
const configuredTargetCount = computed(() => (
  state.algorithm === 'GB_SFLA_CS'
    ? scenarioPlan.value.threatCount
    : scenarioPlan.value.targetCount
))
const missionPhase = computed(() => currentAlgorithmFrame.value?.phase || (state.mission === 'RUNNING' ? 'TRANSIT' : 'READY'))
const missionMetrics = computed(() => currentAlgorithmFrame.value?.metrics ?? {})
const visibleTargetCount = computed(() => currentAlgorithmFrame.value?.targets.filter(target => target.visible !== false).length ?? configuredTargetCount.value)
const missionProgress = computed(() => Math.round(Number(
  missionMetrics.value.missionProgress ?? missionMetrics.value.progress ?? 0,
) * 100))
const escortProgress = computed(() => Math.round(Number(missionMetrics.value.escortProgress ?? 0) * 100))
const captureProgress = computed(() => Math.round(Number(missionMetrics.value.captureProgress ?? 0) * 100))
const captureRemainingSeconds = computed(() => Math.max(0, Math.ceil(Number(missionMetrics.value.captureRemainingFrames ?? 0) / 10)))
const captureGroups = computed(() => Array.isArray(missionMetrics.value.captureGroups)
  ? missionMetrics.value.captureGroups as CaptureGroupMetric[]
  : [])
const roleSummary = computed(() => {
  const roles = missionMetrics.value.roles
  if (!roles || typeof roles !== 'object') return ''
  return Object.entries(roles as Record<string, unknown>)
    .map(([role, count]) => `${role} ${Number(count)}`)
    .join(' · ')
})
let previousAlgorithmPoses: VirtualPoseStateMap = new Map()
let algorithmPollTimer: number | null = null
let algorithmPollInFlight = false
let algorithmPreparePromise: Promise<boolean> | null = null
const fleetOriginEnu: EnuOrigin = {
  // Centre the experiment in open water instead of beside the island base.
  // The capture target occupies this origin and both containment rings are
  // generated around it, so the complete mission moves as one formation.
  eastM: -360,
  northM: -285,
  upM: 0,
}

const state = reactive({
  algorithm: 'GB_SFLA_CS',
  seed: 20260814,
  uavCount: 3,
  usvCount: 3,
  uavSpeed: 5,
  usvSpeed: 3,
  mission: 'STOPPED',
  runId: 7001,
  sequence: 0,
})

const algorithmDescription = computed(() => state.algorithm === 'GB_SFLA_CS'
  ? '算法负责目标分配、围捕航点、设备速度方向和捕获状态。'
  : '算法负责威胁方向、阻断点、护航弧和混合 UAV/USV 守卫轨迹。')

const speedValid = computed(() =>
  state.uavSpeed >= 0
  && state.uavSpeed <= 15
  && state.usvSpeed >= 0
  && state.usvSpeed <= 4)

const vehicleCodes = computed(() => [
  ...Array.from({ length: state.uavCount }, (_, index) => `UAV-${String(index + 1).padStart(3, '0')}`),
  ...Array.from({ length: state.usvCount }, (_, index) => `USV-${String(index + 1).padStart(3, '0')}`),
])

function addLog(message: string) {
  logs.value.unshift(`${new Date().toLocaleTimeString()}  ${message}`)
  logs.value = logs.value.slice(0, 12)
}

function send(type: string, payload: Record<string, unknown> = {}) {
  const requestId = unityPanel.value?.postToUnity(type, payload)
  addLog(`${type}${requestId ? ` / ${requestId}` : ''}`)
  return requestId
}

function onUnityReady() {
  unityReady.value = true
  addLog('platformBridgeReady: Unity WebGL 已连接')
  send('initializePlatform', {
    runtimeMode: 'VIRTUAL_SIMULATION',
    protocolVersion: '2.0',
    buildId: 'vue-virtual-fleet-v2-compatible',
  })
}

function onUnityError(message: string) {
  unityReady.value = false
  scenarioLoading.value = false
  addLog(`Unity 错误: ${message}`)
}

function onUnityMessage(message: UnityMessage) {
  if (message.type !== 'vueCommandReceived') {
    lastMessage.value = message
  }
  if (message.type === 'vueCommandReceived' && message.payload?.type === 'loadScenario') {
    addLog(
      `bridge loadScenario: sent=${message.payload.bridgeSent === true}`
      + ` queued=${message.payload.queued === true}`
      + ` fallback=${String(message.payload.fallback ?? '') || '-'}`,
    )
  }
  if (message.type === 'unityBridgeError') {
    addLog(
      `Unity bridge error: ${String(message.payload?.message ?? 'unknown')}`
      + ` type=${String(message.payload?.requestedType ?? '-')}`,
    )
  }
  if (message.type === 'platformBridgeReady') {
    unityReady.value = message.payload?.ready === true
      || (
        message.payload?.controlsReady === true
        && message.payload?.cameraReady === true
        && message.payload?.algorithmReady === true
      )
  }
  if (message.type === 'scenarioReady') {
    const readyRunId = Number(message.payload?.runId ?? 0)
    const success = message.payload?.success === true
    // Some compatible Unity builds omit runId from scenarioReady. Accept a
    // missing id for the currently loading scenario, but never accept a
    // positive id belonging to an older scenario.
    const runIdMatches = readyRunId === state.runId || readyRunId === 0
    scenarioReadyRunId.value = success && runIdMatches
      ? (readyRunId || state.runId)
      : null
    if (success && runIdMatches) {
      const returnedPoses = Array.isArray(message.payload?.initialPoses)
        ? message.payload.initialPoses
          .filter((pose): pose is ScenarioInitialPose => (
            typeof pose === 'object'
            && pose !== null
            && typeof (pose as Record<string, unknown>).deviceCode === 'string'
          ))
          .map(pose => ({
            deviceCode: pose.deviceCode,
            deviceType: pose.deviceType,
            eastM: Number(pose.eastM),
            northM: Number(pose.northM),
            upM: Number(pose.upM),
            headingDeg: Number(pose.headingDeg ?? 0),
            speedMps: Number(pose.speedMps ?? 0),
            state: pose.state,
            valid: pose.valid !== false,
          }))
          .filter(pose => (
            Number.isFinite(pose.eastM)
            && Number.isFinite(pose.northM)
            && Number.isFinite(pose.upM)
            && Number.isFinite(pose.headingDeg)
          ))
        : []
      initialScenarioPoses.value = returnedPoses.length > 0
        ? returnedPoses
        : plannedScenarioPoses.value
      addLog(`scenario initial poses: ${initialScenarioPoses.value.length}`)
    }
    if (runIdMatches) scenarioLoading.value = false
    if (success && runIdMatches) void prepareExternalAlgorithm()
    addLog(
      `scenarioReady: ${success ? 'success' : 'failed'}`
      + ` runId=${readyRunId || '-'}`,
    )
  }
  if (message.type === 'poseFrameApplied') {
    const success = message.payload?.success === true
    const code = String(message.payload?.code ?? '')
    const trackedDeviceCode = String(message.payload?.trackedDeviceCode ?? '')
    const unityPosition = trackedDeviceCode
      ? ` ${trackedDeviceCode} unity=(${Number(message.payload?.unityPositionX ?? 0).toFixed(2)},`
        + `${Number(message.payload?.unityPositionY ?? 0).toFixed(2)},`
        + `${Number(message.payload?.unityPositionZ ?? 0).toFixed(2)})`
        + ` heading=${Number(message.payload?.unityHeadingDeg ?? 0).toFixed(1)}`
        + ` model=(${Number(message.payload?.transformPositionX ?? 0).toFixed(2)},`
        + `${Number(message.payload?.transformPositionY ?? 0).toFixed(2)},`
        + `${Number(message.payload?.transformPositionZ ?? 0).toFixed(2)})`
        + ` heading=${Number(message.payload?.transformHeadingDeg ?? 0).toFixed(1)}`
      : ''
    addLog(
      `poseFrameApplied: sequence=${message.payload?.sequence ?? '-'}`
      + ` ${success ? 'success' : code || 'failed'}`
      + trackedDeviceCode
      + unityPosition,
    )
  }
  if (message.type === 'cameraChanged') {
    const mode = String(message.payload?.mode ?? '').trim().toLowerCase()
    const deviceCode = String(message.payload?.deviceCode ?? '').trim()
    if (mode) cameraMode.value = mode
    if (mode === 'overview') selectedDevice.value = ''
    else if (deviceCode) selectedDevice.value = deviceCode
    addLog(`cameraChanged: ${deviceCode || '-'} / ${mode || '-'}`)
  }
}

function validateSpeed(value: number, max: number) {
  return Math.max(0, Math.min(max, Number.isFinite(value) ? value : 0))
}

function validateFleetCount(value: number) {
  return Math.max(1, Math.min(128, Math.trunc(Number.isFinite(value) ? value : 1)))
}

function generateScenario() {
  if (sceneLocked.value || scenarioLoading.value) return
  state.uavSpeed = validateSpeed(state.uavSpeed, 15)
  state.usvSpeed = validateSpeed(state.usvSpeed, 4)
  state.uavCount = validateFleetCount(state.uavCount)
  state.usvCount = validateFleetCount(state.usvCount)
  // The Unity scene has a verified open-water operating box southwest of
  // Catalina.  Keep the algorithm's complete local safety domain inside it:
  // global east [-510,-210], north [-435,-135].  Scaling the origin with the
  // UI "world size" previously moved fleets onto the decorative outer coast.
  fleetOriginEnu.eastM = -360
  fleetOriginEnu.northM = -285
  // Standalone virtual simulation uses one isolated ID across Unity and the
  // algorithm process. It does not require a MissionRun database record.
  state.runId = Date.now()
  state.sequence = 0
  state.mission = 'STOPPED'
  missionActionMessage.value = ''
  algorithmPrepared.value = false
  algorithmPreparePromise = null
  stopAlgorithmPolling()
  previousAlgorithmPoses = new Map()
  currentAlgorithmFrame.value = null
  plannedScenarioPoses.value = buildVirtualFleetGridLayout({
    uavCount: state.uavCount,
    usvCount: state.usvCount,
    fleetOrigin: fleetOriginEnu,
    uavSpeedMps: state.uavSpeed,
    usvSpeedMps: state.usvSpeed,
    captureMode: state.algorithm === 'GB_SFLA_CS',
    seed: state.seed,
  })
  // The observer must own the camera before a mission starts; otherwise the
  // legacy chase camera consumes wheel and drag input until the user clicks
  // the overview button once.
  window.setTimeout(() => setOverviewCamera(), 80)
  initialScenarioPoses.value = plannedScenarioPoses.value
  scenarioReadyRunId.value = null
  scenarioLoading.value = true
  addLog(`loadScenario pending: runId=${state.runId}`)
  send('loadScenario', {
    runtimeMode: 'VIRTUAL_SIMULATION',
    algorithmCode: state.algorithm,
    runId: state.runId,
    uavCount: state.uavCount,
    usvCount: state.usvCount,
    targetCount: configuredTargetCount.value,
    layoutVersion: state.algorithm === 'ESCORT_GUARD' ? 'ADAPTIVE_MULTI_TARGET_V2' : 'ADAPTIVE_MULTI_CAPTURE_V2',
    initialPosesCoordinateFrame: 'GLOBAL_ENU',
    initialPoses: plannedScenarioPoses.value,
    initialSpeedMps: state.algorithm === 'GB_SFLA_CS' ? state.uavSpeed : state.usvSpeed,
    seed: state.seed,
  })
}

function prepareExternalAlgorithm(): Promise<boolean> {
  if (algorithmPrepared.value) return Promise.resolve(true)
  if (scenarioLoading.value) return Promise.resolve(false)
  if (algorithmPreparePromise) return algorithmPreparePromise

  const prepareRunId = state.runId
  algorithmPreparing.value = true
  algorithmPreparePromise = (async () => {
    try {
      const status = await prepareAlgorithmRun(prepareRunId, state.algorithm, {
      uavCount: state.uavCount,
      usvCount: state.usvCount,
      targetCount: configuredTargetCount.value,
      protectedCount: state.algorithm === 'ESCORT_GUARD' ? scenarioPlan.value.protectedCount : 0,
      threatCount: scenarioPlan.value.threatCount,
      simultaneousThreats: scenarioPlan.value.simultaneousThreats,
      worldWidth: scenarioPlan.value.worldWidth,
      worldHeight: scenarioPlan.value.worldHeight,
      adaptiveMultiTarget: state.algorithm === 'ESCORT_GUARD',
      seed: state.seed,
      uavSpeedMps: state.uavSpeed,
      usvSpeedMps: state.usvSpeed,
      coordinateFrame: 'FLEET_LOCAL_ENU',
      initialPosesCoordinateFrame: 'GLOBAL_ENU',
      fleetOrigin: fleetOriginEnu,
      initialPoses: initialScenarioPoses.value,
      targetBehavior: 'MOVING',
      previewEnabled: state.algorithm === 'GB_SFLA_CS',
      threatMinDistanceM: state.algorithm === 'GB_SFLA_CS' ? 90 : 120,
      standaloneVirtualSimulation: true,
      })
      if (state.runId !== prepareRunId) return false
      algorithmPrepared.value = true
      // PREVIEW keeps producing frames after prepare. Start at zero so the
      // first poll applies the authoritative ambient positions instead of
      // skipping directly to the latest sequence number reported by status.
      state.sequence = 0
      addLog(`algorithm prepared: ${state.algorithm} runId=${prepareRunId}`)
      if (state.algorithm === 'GB_SFLA_CS') startAlgorithmPolling()
      return true
    } catch (error) {
      algorithmPrepared.value = false
      addLog(`algorithm prepare failed: ${error instanceof Error ? error.message : String(error)}`)
      return false
    } finally {
      algorithmPreparing.value = false
      algorithmPreparePromise = null
    }
  })()
  return algorithmPreparePromise
}

async function startMission() {
  missionActionMessage.value = ''
  if (
    !unityReady.value
    || !speedValid.value
    || scenarioLoading.value
    || scenarioReadyRunId.value !== state.runId
  ) {
    missionActionMessage.value = scenarioLoading.value || scenarioReadyRunId.value !== state.runId
      ? '场景仍在等待 Unity 确认，请重新生成场景或查看回执日志。'
      : !unityReady.value
        ? 'Unity WebGL 尚未就绪，暂时不能启动算法。'
        : '速度配置无效，请修正后再启动。'
    addLog(`missionStart blocked: ${missionActionMessage.value} runId=${state.runId}`)
    return
  }
  if (!algorithmPrepared.value) {
    addLog(`missionStart: preparing algorithm runId=${state.runId}`)
    if (!(await prepareExternalAlgorithm())) {
      missionActionMessage.value = '算法准备失败，请查看回执日志中的具体错误。'
      return
    }
  }
  const initialFrameSynced = await synchronizeInitialAlgorithmFrame()
  if (!initialFrameSynced) {
    missionActionMessage.value = '算法首帧未返回，任务未启动；请查看回执日志。'
    addLog(`missionStart blocked: ${missionActionMessage.value}`)
    return
  }
  try {
    await controlAlgorithmRun(state.runId, 'start')
    state.mission = 'RUNNING'
    missionActionMessage.value = '算法已启动。'
    addLog(
      `algorithm coordinates: FLEET_LOCAL_ENU`
      + ` origin=(${fleetOriginEnu.eastM},${fleetOriginEnu.northM},${fleetOriginEnu.upM})`,
    )
    send('missionStart', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
    startAlgorithmPolling()
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (/停止|stop|not found|不存在/i.test(message)) {
      algorithmPrepared.value = false
      algorithmPreparePromise = null
      addLog(`algorithm process unavailable, rebuilding runId=${state.runId}`)
      if (await prepareExternalAlgorithm()) {
        const retryInitialFrameSynced = await synchronizeInitialAlgorithmFrame()
        if (!retryInitialFrameSynced) {
          addLog(`missionStart retry blocked: algorithm sequence=1 is not available`)
          return
        }
        try {
          await controlAlgorithmRun(state.runId, 'start')
          state.mission = 'RUNNING'
          send('missionStart', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
          startAlgorithmPolling()
          return
        } catch (retryError) {
          addLog(
            `missionStart retry failed: ${
              retryError instanceof Error ? retryError.message : String(retryError)
            }`,
          )
          return
        }
      }
    }
    missionActionMessage.value = `启动失败：${message}`
    addLog(`missionStart failed: ${message}`)
  }
}

async function pauseMission() {
  if (state.mission !== 'RUNNING') return
  try {
    await controlAlgorithmRun(state.runId, 'pause')
    state.mission = 'PAUSED'
    stopAlgorithmPolling()
    send('missionPause', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
  } catch (error) {
    addLog(`missionPause failed: ${error instanceof Error ? error.message : String(error)}`)
  }
}

function toggleWebglExpanded() {
  webglExpanded.value = !webglExpanded.value
}

async function stopMission() {
  try {
    if (algorithmPrepared.value) await controlAlgorithmRun(state.runId, 'stop')
    state.mission = 'STOPPED'
    algorithmPrepared.value = false
    algorithmPreparePromise = null
    stopAlgorithmPolling()
    currentAlgorithmFrame.value = null
    send('missionStop', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
  } catch (error) {
    addLog(`missionStop failed: ${error instanceof Error ? error.message : String(error)}`)
  }
}

async function resetMission() {
  stopAlgorithmPolling()
  if (algorithmPrepared.value) {
    try {
      await controlAlgorithmRun(state.runId, 'cancel')
    } catch (error) {
      addLog(`algorithm reset warning: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  state.mission = 'STOPPED'
  state.sequence = 0
  algorithmPrepared.value = false
  algorithmPreparePromise = null
  previousAlgorithmPoses = new Map()
  currentAlgorithmFrame.value = null
  plannedScenarioPoses.value = []
  initialScenarioPoses.value = []
  scenarioReadyRunId.value = null
  selectedDevice.value = ''
  logs.value = []
  addLog('missionReset: 清理算法、轨迹和 Unity 运行实例')
  send('missionReset', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
  unityPanel.value?.reload()
}

async function applyAlgorithmFrame(
  frame: AlgorithmRuntimeFrame,
  force = false,
) {
  if (!force && frame.sequence <= state.sequence) return
  const adapted = adaptVirtualAlgorithmFrame(
    frame,
    previousAlgorithmPoses,
    { fleetOrigin: fleetOriginEnu },
  )
  previousAlgorithmPoses = adapted.nextState
  currentAlgorithmFrame.value = frame
  state.sequence = frame.sequence
  const trackedPose = adapted.payload.vehicles.find((pose) => pose.deviceCode === 'UAV-001')
  const targetPose = adapted.payload.targets.find((pose) => pose.deviceCode === 'TARGET-001')
  addLog(
    `algorithm frame: sequence=${frame.sequence}`
    + (trackedPose
      ? ` UAV-001 pos=(${trackedPose.eastM.toFixed(2)},`
        + `${trackedPose.northM.toFixed(2)},${trackedPose.upM.toFixed(2)})`
        + ` heading=${trackedPose.headingDeg.toFixed(1)}`
      : '')
    + (targetPose
      ? ` TARGET-001 pos=(${targetPose.eastM.toFixed(2)},`
        + `${targetPose.northM.toFixed(2)},${targetPose.upM.toFixed(2)})`
      : ''),
  )
  send('applyPoseBatch', { ...adapted.payload, runId: state.runId })
  if (frame.terminalStatus) {
    const terminal = frame.terminalStatus.toUpperCase()
    state.mission = terminal
    stopAlgorithmPolling()
    algorithmPrepared.value = false
    algorithmPreparePromise = null
    addLog(`mission terminal: ${terminal} ${String(frame.metrics.terminalReason ?? '')}`)
    send('missionStop', {
      runtimeMode: 'VIRTUAL_SIMULATION',
      runId: state.runId,
      terminalStatus: terminal,
    })
  }
}

async function synchronizeInitialAlgorithmFrame(): Promise<boolean> {
  try {
    const frames = await fetchAlgorithmFrames(state.runId, 0)
    const firstFrame = [...frames]
      .filter(frame => frame.sequence > 0)
      .sort((left, right) => right.sequence - left.sequence)[0]

    if (!firstFrame) {
      addLog(`algorithm initial frame unavailable: runId=${state.runId}`)
      return false
    }

    await applyAlgorithmFrame(firstFrame, true)
    const targetPose = adaptVirtualAlgorithmFrame(
      firstFrame,
      new Map(),
      { fleetOrigin: fleetOriginEnu },
    ).payload.targets.find(pose => pose.deviceCode === 'TARGET-001')
    addLog(
      `latest preview pose synchronized before missionStart`
      + (targetPose
        ? ` TARGET-001=(${targetPose.eastM.toFixed(2)},${targetPose.northM.toFixed(2)},${targetPose.upM.toFixed(2)})`
        : ' TARGET-001=missing'),
    )
    return true
  } catch (error) {
    addLog(
      `algorithm initial frame failed: ${
        error instanceof Error ? error.message : String(error)
      }`,
    )
    return false
  }
}

async function pollAlgorithmFrame() {
  if (
    algorithmPollInFlight
    || (
      state.mission !== 'RUNNING'
      && !(state.algorithm === 'GB_SFLA_CS' && state.mission === 'STOPPED')
    )
    || !algorithmPrepared.value
    || !unityReady.value
  ) return
  algorithmPollInFlight = true
  try {
    const frames = await fetchAlgorithmFrames(state.runId, state.sequence)
    for (const frame of frames) {
      await applyAlgorithmFrame(frame)
    }
  } catch (error) {
    addLog(`algorithm frame failed: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    algorithmPollInFlight = false
  }
}

function startAlgorithmPolling() {
  stopAlgorithmPolling()
  void pollAlgorithmFrame()
  algorithmPollTimer = window.setInterval(() => {
    void pollAlgorithmFrame()
  }, 100)
}

function stopAlgorithmPolling() {
  if (algorithmPollTimer !== null) {
    window.clearInterval(algorithmPollTimer)
    algorithmPollTimer = null
  }
}

function selectDevice(code: string) {
  selectedDevice.value = code
  cameraMode.value = 'device-follow'
  send('selectDevice', { deviceCode: code })
}

function followSelectedDevice() {
  if (!selectedDevice.value) return
  send('setCameraMode', {
    mode: 'device-follow',
    deviceCode: selectedDevice.value,
  })
}

function setOverviewCamera() {
  send('setCameraMode', { mode: 'overview' })
}

onBeforeUnmount(() => {
  stopAlgorithmPolling()
})
</script>

<template>
  <ConsoleLayout
    title="算法仿真"
    eyebrow="VIRTUAL FLEET / UNITY BRIDGE V3"
    :show-refresh="false"
  >
    <div class="virtual-fleet-page">
      <div class="vf-grid">
        <aside class="vf-column">
          <section class="vf-panel">
            <div class="vf-panel-head"><h3>场景配置</h3><span>V3 PROTOCOL</span></div>
            <label>算法
              <select v-model="state.algorithm" :disabled="sceneLocked">
                <option value="GB_SFLA_CS">GB-SFLA-CS 协同围捕（模拟）</option>
                <option value="ESCORT_GUARD">混合 UAV/USV 护航守卫（模拟）</option>
              </select>
            </label>
            <p class="vf-description">{{ algorithmDescription }}</p>
            <div v-if="state.algorithm === 'ESCORT_GUARD'" class="vf-plan-summary">
              <strong>{{ scenarioPlan.protectedCount }} 护航目标 · {{ scenarioPlan.threatCount }} 敌船</strong>
              <span>同时来袭 {{ scenarioPlan.simultaneousThreats }} · 世界 {{ scenarioPlan.worldWidth }}×{{ scenarioPlan.worldHeight }} m</span>
              <small>{{ scenarioPlan.realtimeTier === 'PHASE_TWO_REALTIME' ? '30+30 内实时验收档' : '31–128 容量档（不承诺实时帧率）' }}</small>
            </div>
            <div class="vf-two-col">
              <label>UAV 数量
                <input v-model.number="state.uavCount" type="number" min="1" max="128" :disabled="sceneLocked">
              </label>
              <label>USV 数量
                <input v-model.number="state.usvCount" type="number" min="1" max="128" :disabled="sceneLocked">
              </label>
              <label>UAV 巡航速度 m/s
                <input v-model.number="state.uavSpeed" type="number" min="0" max="15" step="0.1" :disabled="sceneLocked">
                <small>上限 15 m/s</small>
              </label>
              <label>USV 巡航速度 m/s
                <input v-model.number="state.usvSpeed" type="number" min="0" max="4" step="0.1" :disabled="sceneLocked">
                <small>上限 4 m/s</small>
              </label>
            </div>
            <label>随机种子
              <input v-model.number="state.seed" type="number" step="1" :disabled="sceneLocked">
            </label>
            <div class="vf-actions">
              <button class="vf-button primary" type="button" :disabled="sceneLocked || !unityReady || scenarioLoading" @click="generateScenario">
                <RefreshCw :size="15" /> 生成场景
              </button>
              <button class="vf-button" type="button" :disabled="!unityReady" @click="resetMission">
                <CircleStop :size="15" /> 重置
              </button>
            </div>
          </section>

          <section class="vf-panel">
            <div class="vf-panel-head"><h3>任务控制</h3><span>{{ state.mission }}</span></div>
            <div class="vf-actions">
              <button class="vf-button success" type="button" :disabled="state.mission === 'RUNNING' || !unityReady || !speedValid || scenarioLoading || algorithmPreparing || scenarioReadyRunId !== state.runId" @click="startMission">
                <Play :size="15" /> {{ algorithmPreparing ? '准备中' : '开始' }}
              </button>
              <button class="vf-button" type="button" :disabled="state.mission !== 'RUNNING'" @click="pauseMission">
                <Pause :size="15" /> 暂停
              </button>
              <button class="vf-button danger" type="button" :disabled="state.mission === 'STOPPED'" @click="stopMission">
                <CircleStop :size="15" /> 停止
              </button>
            </div>
            <p v-if="!speedValid" class="vf-error">速度超过协议上限，请修正后再开始任务。</p>
            <p v-if="missionActionMessage" class="vf-action-message">{{ missionActionMessage }}</p>
          </section>

          <section class="vf-panel">
            <div class="vf-panel-head"><h3>回执日志</h3><span>{{ logs.length }} EVENTS</span></div>
            <div class="vf-log">
              <div v-for="entry in logs" :key="entry">{{ entry }}</div>
              <span v-if="!logs.length">等待 Unity 回执...</span>
            </div>
          </section>
        </aside>

        <section class="vf-stage-panel" :class="{ expanded: webglExpanded }">
          <div class="vf-stage-head">
            <div><h3>Unity WebGL 虚拟场景</h3><span>独立运行实例：virtual-fleet-v3-01</span></div>
            <div class="vf-stage-actions">
              <strong>{{ state.uavCount }} UAV / {{ state.usvCount }} USV</strong>
              <button class="vf-expand" type="button" @click="toggleWebglExpanded">
                <Minimize2 v-if="webglExpanded" :size="16" />
                <Maximize2 v-else :size="16" />
                {{ webglExpanded ? '退出放大' : '放大画面' }}
              </button>
            </div>
          </div>
          <div class="vf-unity-stage">
            <UnityWebglPanel
              ref="unityPanel"
              iframe-src="/unity-virtual-fleet/index.html?embedded=1&build=20260821-v7"
              runtime-scope="VIRTUAL_FLEET"
              runtime-instance-id="virtual-fleet-v3-01"
              @unity-ready="onUnityReady"
              @unity-error="onUnityError"
              @unity-message="onUnityMessage"
            />
          </div>
          <div class="vf-mission-rail">
            <span><i class="live"></i>阶段 <strong>{{ missionPhase }}</strong></span>
            <span>综合进度 <strong>{{ missionProgress }}%</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">护航 <strong>{{ escortProgress }}%</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">围捕 <strong>{{ captureProgress }}%</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">进攻敌船 <strong>{{ Number(missionMetrics.attackingThreatCount ?? 0) }}</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">已建立拦截 <strong>{{ Number(missionMetrics.interceptedThreatCount ?? 0) }}</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">敌船均速 <strong>{{ Number(missionMetrics.threatMeanSpeedMps ?? 0).toFixed(1) }} m/s</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD'">护航目标速度 <strong>{{ Number(missionMetrics.protectedTargetMeanSpeedMps ?? 0).toFixed(1) }} m/s</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD' && missionMetrics.closestThreatDistanceM != null">当前最近威胁 <strong>{{ Number(missionMetrics.closestThreatDistanceM).toFixed(1) }} m</strong></span>
            <span v-if="state.algorithm === 'ESCORT_GUARD' && captureGroups.length">围捕剩余 <strong>{{ captureRemainingSeconds }} s</strong></span>
            <span>可见目标 <strong>{{ visibleTargetCount }}</strong></span>
            <span>避障修正 <strong>{{ Number(missionMetrics.avoidanceCount ?? 0) }}</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">包围完成 <strong>{{ missionMetrics.formationReady === true ? '是' : '进行中' }}</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">敌船速度 <strong>{{ Number(missionMetrics.targetSpeedMps ?? 0).toFixed(1) }} m/s</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">敌船行为 <strong>{{ String(missionMetrics.targetBehavior ?? '-') }}</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">追逃 <strong>{{ Number(missionMetrics.targetTravelDistanceM ?? 0).toFixed(0) }}/{{ Number(missionMetrics.requiredPursuitDistanceM ?? 0).toFixed(0) }} m</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">闭环置信 <strong>{{ Math.round(Number(missionMetrics.containmentConfidence ?? 0) * 100) }}%</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS' && missionMetrics.captureBlocker !== 'NONE'">阻塞 <strong>{{ String(missionMetrics.captureBlocker ?? '-') }}</strong></span>
            <span v-if="state.algorithm === 'GB_SFLA_CS'">重规划 <strong>{{ Number(missionMetrics.replanCount ?? 0) }}</strong></span>
            <span v-else>已捕获 <strong>{{ Number(missionMetrics.capturedThreatCount ?? 0) }} / {{ scenarioPlan.threatCount }}</strong></span>
            <span v-if="missionMetrics.minProtectedThreatDistanceM != null">护航安全距离 <strong>{{ Number(missionMetrics.minProtectedThreatDistanceM).toFixed(1) }} m</strong></span>
            <span v-if="missionMetrics.minShoreDistanceM != null">岸线余量 <strong>{{ Number(missionMetrics.minShoreDistanceM).toFixed(1) }} m</strong></span>
          </div>
          <div v-if="captureGroups.length" class="vf-capture-rail">
            <span v-for="group in captureGroups" :key="group.threatCode">
              <strong>{{ group.threatCode }}</strong>
              {{ group.state }} · 阶段 {{ Number(group.stage ?? 0) + 1 }}/3 ·
              意图 {{ group.intent || '-' }} ·
              {{ group.uavCount }} UAV + {{ group.usvCount }} USV ·
              追逃 {{ Number(group.pursuitDistanceM ?? 0).toFixed(0) }}/{{ Number(group.requiredPursuitDistanceM ?? 0).toFixed(0) }} m ·
              到位 {{ Math.round(Number(group.arrivalRatio ?? 0) * 100) }}% ·
              保持 {{ group.holdFrames ?? 0 }}/{{ group.holdRequiredFrames ?? 0 }}
            </span>
          </div>
          <div v-if="roleSummary" class="vf-role-rail">角色分工：{{ roleSummary }}</div>
          <div class="vf-camera-tip">滚轮以指针位置缩放 · 左键/中键拖动平移 · 右键拖动旋转 · 双指缩放 · 双击恢复全局</div>
          <div class="vf-device-strip">
            <div class="vf-strip-head"><h3>设备选择</h3><span>点击设备后可切换跟随视角</span></div>
            <div class="vf-device-list">
              <button
                v-for="code in vehicleCodes.slice(0, 12)"
                :key="code"
                class="vf-device"
                :class="{ selected: selectedDevice === code, usv: code.startsWith('USV-') }"
                type="button"
                @click="selectDevice(code)"
              >
                <SquareStack :size="14" />
                {{ code }}
              </button>
            </div>
            <button class="vf-follow" type="button" :disabled="!selectedDevice || !unityReady" @click="followSelectedDevice">
              <Camera :size="15" /> 跟随 {{ selectedDevice || '选中设备' }}
            </button>
            <button
              class="vf-follow"
              :class="{ active: cameraMode === 'overview' }"
              type="button"
              :disabled="!unityReady"
              :aria-pressed="cameraMode === 'overview'"
              @click="setOverviewCamera"
            >
              <Camera :size="15" /> 全局俯视
            </button>
          </div>
        </section>

        <aside class="vf-column">
          <section class="vf-panel">
            <div class="vf-panel-head"><h3>协议状态</h3><span>LIVE</span></div>
            <dl class="vf-status-list">
              <div><dt>运行模式</dt><dd>VIRTUAL_SIMULATION</dd></div>
              <div><dt>算法</dt><dd>{{ state.algorithm }}</dd></div>
              <div><dt>任务状态</dt><dd>{{ state.mission }}</dd></div>
              <div><dt>序列号</dt><dd>{{ state.sequence }}</dd></div>
              <div><dt>选中设备</dt><dd>{{ selectedDevice || '无' }}</dd></div>
            </dl>
          </section>
          <section class="vf-panel vf-debug-panel">
            <details>
              <summary>调试回执 <span>{{ lastMessage?.type || 'NONE' }}</span></summary>
              <pre>{{ JSON.stringify(lastMessage || {}, null, 2) }}</pre>
            </details>
          </section>
          <section class="vf-panel">
            <div class="vf-panel-head"><h3>物理速度规则</h3><span>m/s</span></div>
            <div class="vf-speed-rule"><strong>UAV</strong><span>{{ state.uavSpeed.toFixed(1) }} / 15</span></div>
            <div class="vf-speed-bar"><i :style="{ width: `${Math.min(100, state.uavSpeed / 15 * 100)}%` }"></i></div>
            <div class="vf-speed-rule"><strong>USV</strong><span>{{ state.usvSpeed.toFixed(1) }} / 4</span></div>
            <div class="vf-speed-bar usv"><i :style="{ width: `${Math.min(100, state.usvSpeed / 4 * 100)}%` }"></i></div>
            <p class="vf-note">Unity 内部按 PresentationCoordinateScale = 0.18 转换。</p>
          </section>
        </aside>
      </div>
    </div>
  </ConsoleLayout>
</template>

<style scoped>
.virtual-fleet-page { display: grid; gap: 14px; }
.vf-grid { display: grid; grid-template-columns: 270px minmax(620px, 1fr) 250px; gap: 12px; align-items: start; }
.vf-column { display: grid; gap: 14px; }
.vf-panel, .vf-stage-panel { min-width: 0; padding: 15px; color: #dff8f4; background: rgba(8, 25, 30, .94); border: 1px solid rgba(108, 228, 213, .18); border-radius: 8px; }
.vf-panel-head, .vf-stage-head, .vf-strip-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.vf-panel-head { margin-bottom: 13px; }
.vf-panel-head h3, .vf-stage-head h3, .vf-strip-head h3 { margin: 0; color: #effffd; font-size: 15px; }
.vf-panel-head span, .vf-stage-head span, .vf-strip-head span { color: #6f9697; font-size: 10px; }
.vf-panel label { display: grid; gap: 6px; margin-top: 11px; color: #9cc1bd; font-size: 11px; letter-spacing: 0; text-transform: none; }
.vf-panel input, .vf-panel select { min-height: 36px; padding: 0 9px; color: #eafffb; background: #07171c; border: 1px solid #28515a; border-radius: 4px; }
.vf-panel input:disabled, .vf-panel select:disabled { opacity: .55; }
.vf-panel small { color: #6f9697; font-size: 10px; }
.vf-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.vf-description, .vf-note { margin-top: 10px; color: #8fb4b2; font-size: 11px; line-height: 1.6; }
.vf-plan-summary { display: grid; gap: 5px; margin-top: 10px; padding: 10px; border: 1px solid rgba(99,217,231,.24); border-radius: 5px; background: rgba(99,217,231,.05); }
.vf-plan-summary strong { color: #eafffb; font-size: 12px; }
.vf-plan-summary span, .vf-plan-summary small { color: #78aaa9; font-size: 10px; }
.vf-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 13px; }
.vf-button, .vf-follow, .vf-device { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 0 10px; color: #dff8f4; background: rgba(108, 228, 213, .06); border: 1px solid rgba(108, 228, 213, .24); border-radius: 4px; cursor: pointer; }
.vf-button:hover:not(:disabled), .vf-follow:hover:not(:disabled), .vf-device:hover { border-color: #6ce4d5; color: #6ce4d5; }
.vf-follow.active { border-color: #6ce4d5; color: #6ce4d5; background: rgba(108, 228, 213, .14); }
.vf-button.primary { color: #061113; background: #6ce4d5; border-color: #6ce4d5; font-weight: 800; }
.vf-button.success { color: #68e6a8; border-color: rgba(104, 230, 168, .45); }
.vf-button.danger { color: #ff8179; border-color: rgba(255, 129, 121, .44); }
.vf-button.capture { color: #ffcf72; border-color: rgba(255,207,114,.5); }
.vf-button:disabled, .vf-follow:disabled { cursor: not-allowed; opacity: .4; }
.vf-error { margin-top: 10px; color: #ff8179; font-size: 11px; }
.vf-action-message { margin: 10px 0 0; color: #9fe8df; font-size: 11px; line-height: 1.5; }
.vf-stage-panel { padding: 0; overflow: hidden; }
.vf-stage-head { padding: 14px 15px; border-bottom: 1px solid rgba(108, 228, 213, .15); }
.vf-stage-head strong { color: #ffcf72; font-size: 12px; }
.vf-stage-actions { display: flex; align-items: center; gap: 10px; }
.vf-expand { display: inline-flex; align-items: center; gap: 6px; min-height: 30px; padding: 0 9px; color: #dff8f4; background: #092027; border: 1px solid rgba(108,228,213,.3); border-radius: 4px; cursor: pointer; }
.vf-stage-panel.expanded { position: fixed; inset: 10px; z-index: 2100; display: flex; flex-direction: column; background: #031015; box-shadow: 0 0 0 100vmax rgba(0,0,0,.82); }
.vf-stage-panel.expanded .vf-unity-stage { flex: 1; min-height: 0; }
.vf-stage-panel.expanded .vf-unity-stage :deep(.unity-webgl-panel) { height: 100%; }
.vf-unity-stage { min-height: 610px; background: #031015; }
.vf-unity-stage :deep(.unity-webgl-panel) { width: 100%; height: 610px; }
.vf-mission-rail { display: flex; flex-wrap: wrap; gap: 8px 20px; padding: 9px 14px; color: #7ea7a5; background: linear-gradient(90deg, rgba(8,35,41,.98), rgba(5,22,28,.98)); border-top: 1px solid rgba(108,228,213,.16); border-bottom: 1px solid rgba(108,228,213,.1); font-size: 10px; }
.vf-mission-rail span { display: inline-flex; align-items: center; gap: 6px; }
.vf-mission-rail strong { color: #eafffb; font-size: 11px; }
.vf-mission-rail i.live { width: 6px; height: 6px; background: #64e6cd; border-radius: 50%; box-shadow: 0 0 8px #64e6cd; }
.vf-capture-rail { display: flex; flex-wrap: wrap; gap: 6px 16px; padding: 7px 14px; color: #8eb8b5; background: rgba(4, 24, 30, .98); border-bottom: 1px solid rgba(108,228,213,.1); font-size: 10px; }
.vf-capture-rail span { padding-right: 14px; border-right: 1px solid rgba(108,228,213,.14); }
.vf-capture-rail strong { color: #ffd963; }
.vf-role-rail { padding: 7px 14px; overflow: hidden; color: #86aaa8; background: #06171d; border-bottom: 1px solid rgba(108,228,213,.1); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.vf-camera-tip { padding: 6px 12px; color: #6f9697; background: #041318; border-top: 1px solid rgba(108,228,213,.1); font-size: 10px; text-align: center; }
.vf-device-strip { padding: 12px; background: #06171d; border-top: 1px solid rgba(108, 228, 213, .15); }
.vf-device-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
.vf-device { min-height: 29px; padding: 0 8px; color: #f5ce6b; font-size: 10px; }
.vf-device.usv { color: #63d9e7; }
.vf-device.selected { color: #061113; background: #6ce4d5; border-color: #6ce4d5; }
.vf-follow { margin-top: 10px; min-height: 34px; }
.vf-status-list { display: grid; gap: 9px; margin: 0; }
.vf-status-list div { display: flex; justify-content: space-between; gap: 8px; padding-bottom: 8px; border-bottom: 1px solid rgba(141, 165, 169, .13); }
.vf-status-list dt { color: #719397; font-size: 11px; }
.vf-status-list dd { margin: 0; color: #dff8f4; font-size: 11px; text-align: right; }
pre { max-height: 260px; overflow: auto; margin: 0; padding: 10px; color: #bde8e0; background: #061116; border: 1px solid #203c43; font: 10px/1.5 Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
.vf-debug-panel summary { display: flex; justify-content: space-between; cursor: pointer; color: #9cc1bd; font-size: 12px; }
.vf-debug-panel details[open] summary { margin-bottom: 10px; }
.vf-log { max-height: 160px; overflow: auto; color: #8fb4b2; font: 10px/1.7 Consolas, monospace; }
.vf-speed-rule { display: flex; justify-content: space-between; gap: 8px; margin-top: 11px; color: #dff8f4; font-size: 11px; }
.vf-speed-rule span { color: #8fb4b2; }
.vf-speed-bar { height: 5px; margin-top: 5px; overflow: hidden; background: #18343a; border-radius: 3px; }
.vf-speed-bar i { display: block; height: 100%; background: #f5ce6b; }
.vf-speed-bar.usv i { background: #63d9e7; }
@media (max-width: 1600px) { .vf-grid { grid-template-columns: 270px minmax(0, 1fr); } .vf-grid > .vf-column:last-child { grid-column: 1 / -1; grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 800px) { .vf-grid, .vf-grid > .vf-column:last-child { grid-template-columns: 1fr; } .vf-grid > .vf-column:last-child { grid-column: auto; } .vf-unity-stage, .vf-unity-stage :deep(.unity-webgl-panel) { min-height: 360px; height: 360px; } .vf-two-col { grid-template-columns: 1fr; } }
</style>
