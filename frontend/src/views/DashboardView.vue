<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionGroupControl from '@/components/control/MissionGroupControl.vue'
import UnifiedVehicleControl from '@/components/control/UnifiedVehicleControl.vue'
import VehicleGlyph from '@/components/control/VehicleGlyph.vue'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import { sendIntegrationHeartbeat } from '@/api/integration'
import { executeMissionAction, fetchMission, fetchMissions } from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import { issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'
import { useMonitoringStore } from '@/stores/monitoring'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useUnityViewportStore } from '@/stores/unityViewport'
import type { RuntimeNode } from '@/types/monitoring'
import { normalizeOperationalState } from '@/utils/runtimeOperationalState'
import type { MissionDetail, MissionStatus } from '@/types/mission'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

const monitoringStore = useMonitoringStore()
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
const unityViewportStore = useUnityViewportStore()
const selectedDeviceCode = ref('uav-01')
const selectedCameraMode = ref('overview')
const unityConnection = ref('等待 WebGL 构建')
const lastUnityEvent = ref('暂无 Unity 回传事件')
const unityCommandState = ref('等待控制指令')
const commandBusy = ref(false)
const cameraCommandBusy = ref(false)
const commandFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
const operationalStates = ref<Record<string, string | undefined>>({
  'uav-01': 'UNKNOWN',
  'uav-02': 'UNKNOWN',
  'uav-03': 'UNKNOWN',
  'usv-01': 'UNKNOWN',
  'usv-02': 'UNKNOWN',
  'usv-03': 'UNKNOWN',
})
const overviewMissionDevices = ref<Array<{ code: string; name: string; type: 'UAV' | 'USV'; status?: string | null }>>([])
const freshnessClock = ref(Date.now())
const overviewMissionId = ref<number | null>(null)
const overviewMissionName = ref('三机三艇协同围捕')
const overviewMissionStatus = ref<MissionStatus>('READY')
const overviewMissionControlSource = ref('UNKNOWN')
const overviewDeploymentAcknowledged = ref(false)
let poseFrameSequence = 0
let heartbeatTimer: number | null = null
let freshnessTimer: number | null = null
const unityInstanceId = 'overview-unity-01'

const cameraModes = [
  { label: '总览', value: 'overview' },
  { label: '当前设备', value: 'device-follow' },
  { label: '行动视角', value: 'action' },
]

let trajectoryToggleTimer: number | null = null

const expectedObservationDevices = [
  { code: 'usv-01', name: '协同无人艇 1', type: 'USV' as const },
  { code: 'usv-02', name: '协同无人艇 2', type: 'USV' as const },
  { code: 'usv-03', name: '协同无人艇 3', type: 'USV' as const },
  { code: 'uav-01', name: '协同无人机 1', type: 'UAV' as const },
  { code: 'uav-02', name: '协同无人机 2', type: 'UAV' as const },
  { code: 'uav-03', name: '协同无人机 3', type: 'UAV' as const },
]

function normalizeDeviceCode(code: string) {
  return code.trim().toLowerCase()
}

function hasRuntimePosition(node: RuntimeNode) {
  return node.positionX !== null && node.positionY !== null && node.positionZ !== null
}

const runtimeNodeByCode = computed(() => {
  const map = new Map<string, RuntimeNode>()
  monitoringStore.nodes.forEach((node) => map.set(normalizeDeviceCode(node.code), node))
  return map
})

const displayedNodes = computed(() =>
  monitoringStore.nodes.filter((node) => ['UAV', 'USV', 'ROS_NODE', 'UNITY_NODE', 'LIGHTHOUSE'].includes(node.type)),
)

const selectableDevices = computed(() => {
  return expectedObservationDevices.map((expected, index) => {
    const runtime = runtimeNodeByCode.value.get(normalizeDeviceCode(expected.code))
    if (runtime) return runtime
    return {
      id: -(index + 1),
      code: expected.code,
      name: expected.name,
      type: expected.type,
      status: 'UNKNOWN',
      host: null,
      port: null,
      endpoint: '',
      rosNamespace: null,
      lastHeartbeatAt: null,
      heartbeatAgeSeconds: -1,
      source: 'UNITY_SCENE',
      instanceId: null,
      positionX: null,
      positionY: null,
      positionZ: null,
      detail: 'Unity 场景可观察，等待实时遥测',
    } as RuntimeNode
  })
})

const quickControlDevices = computed(() => {
  if (overviewMissionDevices.value.length) return overviewMissionDevices.value
  return selectableDevices.value.map((device) => ({
    code: device.code,
    name: device.name,
    type: device.type as 'UAV' | 'USV',
    status: device.status,
  }))
})

const rosBridgeOnline = computed(() =>
  monitoringStore.nodes.some((node) => node.type === 'ROS_NODE' && node.status === 'ONLINE'),
)
const unityReady = computed(() => unityConnection.value.includes('Unity WebGL 已连接'))
const realtimePoseCount = computed(
  () =>
    monitoringStore.nodes.filter(
      (node) => ['UAV', 'USV'].includes(node.type) && node.status === 'ONLINE' && hasRuntimePosition(node),
    ).length,
)
const onlineNodeCount = computed(() => displayedNodes.value.filter((node) => node.status === 'ONLINE').length)
const taskStateText = computed(() => {
  if (!unityReady.value) return '等待 Unity'
  if (rosBridgeOnline.value && realtimePoseCount.value > 0) return '实时同步'
  if (rosBridgeOnline.value) return '等待位姿'
  return '演示预览'
})
const trajectoryLive = computed(() => {
  freshnessClock.value
  const frame = trajectoryStore.frame
  return unityBridgeStore.connected && !!frame && Date.now() - frame.receivedAt <= 3000
})
const fleetReady = computed(() =>
  quickControlDevices.value.length > 0 && quickControlDevices.value.every(({ code }) => {
    const state = operationalStates.value[normalizeDeviceCode(code)]
    return code.startsWith('uav')
      ? ['AIRBORNE', 'HOLDING'].includes(normalizeOperationalState(state, 'UAV'))
      : ['SAILING', 'HOLDING'].includes(normalizeOperationalState(state, 'USV'))
  }),
)
const readyDeviceCount = computed(() =>
  quickControlDevices.value.filter(({ code }) => {
    const state = operationalStates.value[normalizeDeviceCode(code)]
    return code.startsWith('uav')
      ? ['AIRBORNE', 'HOLDING'].includes(normalizeOperationalState(state, 'UAV'))
      : ['SAILING', 'HOLDING'].includes(normalizeOperationalState(state, 'USV'))
  }).length,
)
const missionGroupProgress = computed(() => {
  if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(overviewMissionStatus.value)) return 100
  if (overviewMissionStatus.value === 'RUNNING' || overviewMissionStatus.value === 'PAUSED') return 72
  return Math.round((readyDeviceCount.value / Math.max(1, quickControlDevices.value.length)) * 48)
})
const missionReadinessText = computed(() =>
  overviewMissionStatus.value === 'RUNNING'
    ? '简单围捕任务执行中'
    : overviewDeploymentAcknowledged.value
      ? `${quickControlDevices.value.length}/${quickControlDevices.value.length} 载具已完成编组部署`
      : `等待部署 ${quickControlDevices.value.length} 台围捕载具`,
)

const overviewFleetCards = computed(() =>
  selectableDevices.value.map((device) => {
    const code = normalizeDeviceCode(device.code)
    const state = normalizeOperationalState(operationalStates.value[code], device.type === 'UAV' ? 'UAV' : 'USV')
    const labels: Record<string, string> = {
      UNKNOWN: '等待遥测', GROUNDED: '地面待命', TAKING_OFF: '起飞中', AIRBORNE: '空中执行',
      HOLDING: '安全保持', RETURNING: '返航中', LANDING: '降落中', MOORED: '靠泊待命',
      DEPARTING: '离泊中', SAILING: '航行中', STOPPED: '已停止', ERROR: '异常',
    }
    return {
      ...device,
      code,
      state,
      stateLabel: labels[state] ?? state,
      feedback: commandFeedback.value[code],
    }
  }),
)

function operationalStateAfterCommand(commandType: RuntimeCommandType) {
  const states: Partial<Record<RuntimeCommandType, string>> = {
    UAV_TAKEOFF: 'AIRBORNE', UAV_HOVER: 'HOLDING', UAV_RESUME: 'AIRBORNE', UAV_RETURN: 'RETURNING', UAV_LAND: 'LANDING',
    USV_DEPART: 'SAILING', USV_HOLD: 'HOLDING', USV_RESUME: 'SAILING', USV_RETURN: 'RETURNING', USV_STOP: 'STOPPED',
  }
  return states[commandType]
}

function toUnityPose(node: RuntimeNode) {
  return {
    code: node.code,
    name: node.name,
    type: node.type,
    status: node.status,
    source: node.source,
    position: [node.positionX, node.positionY, node.positionZ],
    orientation: [0, 0, 0, 1],
    heartbeatAgeSeconds: node.heartbeatAgeSeconds,
    detail: node.detail,
  }
}

function pushPoseFrameToUnity() {
  const poses = monitoringStore.nodes
    .filter((node) => ['UAV', 'USV', 'LIGHTHOUSE'].includes(node.type))
    .filter((node) => node.status === 'ONLINE')
    .filter(hasRuntimePosition)
    .map(toUnityPose)

  if (poses.length === 0) return

  unityBridgeStore.send('poseFrame', {
    sequence: ++poseFrameSequence,
    source: 'spring-monitoring',
    timestampMs: Date.now(),
    poses,
  })
}

function unityHeartbeatDetail() {
  return [
    `Unity WebGL page active`,
    `camera=${selectedCameraMode.value}`,
    `selected=${selectedDeviceCode.value}`,
    `lastEvent=${lastUnityEvent.value}`,
    `commandState=${unityCommandState.value}`,
    `poseFrames=${poseFrameSequence}`,
  ].join(' | ')
}

function unityRosConnectionStatus() {
  if (rosBridgeOnline.value && realtimePoseCount.value > 0) {
    return `ROS pose sync active, vehicles=${realtimePoseCount.value}`
  }
  if (rosBridgeOnline.value) return 'ROS bridge online, waiting for vehicle poses'
  return 'ROS bridge offline or no live pose frame'
}

async function sendUnityHeartbeat(state: 'ONLINE' | 'STOPPED' | 'FAILED' = 'ONLINE') {
  try {
    await sendIntegrationHeartbeat({
      componentCode: 'unity-client-01',
      instanceId: unityInstanceId,
      state,
      detail: state === 'STOPPED' ? 'Unity WebGL page closed or route left' : unityHeartbeatDetail(),
      rosConnectionStatus: unityRosConnectionStatus(),
    })
    if (state !== 'STOPPED') void monitoringStore.refresh({}, true)
  } catch (error) {
    console.warn('Unity heartbeat failed', error)
  }
}

function startUnityHeartbeat() {
  void sendUnityHeartbeat('ONLINE')
  if (heartbeatTimer !== null) return
  heartbeatTimer = window.setInterval(() => {
    void sendUnityHeartbeat('ONLINE')
  }, 2000)
}

function stopUnityHeartbeat() {
  if (heartbeatTimer !== null) {
    window.clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
  void sendUnityHeartbeat('STOPPED')
}

function applyOverviewMissionDetail(detail: MissionDetail) {
  const missionChanged = overviewMissionId.value !== null && overviewMissionId.value !== detail.mission.id
  if (missionChanged || ['DRAFT', 'COMPLETED', 'FAILED', 'CANCELLED'].includes(detail.mission.status)) {
    overviewDeploymentAcknowledged.value = false
  }
  overviewMissionId.value = detail.mission.id
  overviewMissionName.value = detail.mission.name
  overviewMissionStatus.value = detail.mission.status
  const currentRunId = detail.currentRun?.id
  const latestControlEvent = detail.events.find((event) =>
    event.runId === currentRunId && /^(MISSION_CONTROL|SYSTEM_OVERVIEW):/.test(event.source ?? ''),
  )
  overviewMissionControlSource.value = latestControlEvent?.source?.split(':', 1)[0] ?? 'UNKNOWN'
  const bindings = detail.devices.filter((item) => item.type === 'UAV' || item.type === 'USV')
  const requiredBindings = bindings.some((item) => item.required) ? bindings.filter((item) => item.required) : bindings
  overviewMissionDevices.value = requiredBindings
    .filter((item) => item.code)
    .map((item) => ({
      code: normalizeDeviceCode(item.code!),
      name: item.name || item.code!.toUpperCase(),
      type: item.type as 'UAV' | 'USV',
      status: item.status,
    }))
}

async function loadOverviewMission() {
  const result = await fetchMissions({
    type: 'COOPERATIVE_ENCIRCLEMENT',
    page: 0,
    size: 50,
  })
  const priority: MissionStatus[] = ['RUNNING', 'PAUSED', 'READY', 'DRAFT', 'CANCELLED', 'FAILED', 'COMPLETED']
  const mission = priority
    .map((status) => result.records.find((item) => item.status === status))
    .find(Boolean) ?? result.records[0]
  if (!mission) {
    overviewMissionId.value = null
    return null
  }
  const detail = await fetchMission(mission.id)
  applyOverviewMissionDetail(detail)
  return detail
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

async function runOverviewMissionAction(action: MissionAction) {
  if (!overviewMissionId.value) {
    await loadOverviewMission()
  }
  if (!overviewMissionId.value) throw new Error('未找到三机三艇协同围捕任务')

  const missionId = overviewMissionId.value
  const result = await executeMissionAction(missionId, action, 'SYSTEM_OVERVIEW')
  applyOverviewMissionDetail(result.detail)

  if (result.command) {
    if (result.command.status === 'FAILED' || result.command.status === 'TIMEOUT') {
      throw new Error(result.command.detail || '任务指令未能下发')
    }
    if (!unityBridgeStore.connected) throw new Error('Unity WebGL 尚未连接，无法确认任务指令')
    const acknowledgement = await unityBridgeStore.sendControlCommandAndWait(
      missionUnityCommand(action),
      '',
      result.command.commandKey,
    )
    if (!acknowledgement.success) {
      throw new Error(acknowledgement.status || 'Unity 未确认任务指令')
    }
  }

  const confirmed = await fetchMission(missionId)
  applyOverviewMissionDetail(confirmed)
  return confirmed
}

async function recordRuntimeCommand(
  commandType: RuntimeCommandType,
  detail: string,
  deviceCode = selectedDeviceCode.value,
  payload?: Record<string, unknown>,
) {
  try {
    return await issueRuntimeCommand({
      commandType,
      deviceCode,
      payload: JSON.stringify({ source: 'SYSTEM_OVERVIEW', ...(payload ?? {}) }),
      detail,
      runtimeScope: 'SYSTEM_OVERVIEW',
      runtimeInstanceId: unityInstanceId,
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '控制指令下发失败')
    throw error
  }
}

async function sendTrackedUnityCommand(
  commandType: RuntimeCommandType,
  detail: string,
  bridgeType: string,
  payload: Record<string, unknown>,
  deviceCode = selectedDeviceCode.value,
) {
  if (cameraCommandBusy.value) throw new Error('上一条视角指令仍在确认中')
  if (!unityBridgeStore.connected) throw new Error('Unity WebGL 尚未连接')
  cameraCommandBusy.value = true
  try {
    const result = await recordRuntimeCommand(commandType, detail, deviceCode, payload)
    if (result.status === 'FAILED' || result.status === 'TIMEOUT') {
      throw new Error(result.detail || '后端未能创建 Unity 指令')
    }
    const acknowledgement = await unityBridgeStore.sendAndWait(
      bridgeType,
      payload,
      result.commandKey,
    )
    if (!acknowledgement.success) throw new Error(acknowledgement.status || 'Unity 未确认指令')
    return acknowledgement
  } finally {
    cameraCommandBusy.value = false
  }
}

async function selectDevice(deviceCode: string) {
  try {
    await sendTrackedUnityCommand('SELECT_DEVICE', '系统总览选择协同设备', 'selectDevice', { deviceCode }, deviceCode)
    selectedDeviceCode.value = deviceCode
    selectedCameraMode.value = 'device-follow'
    lastUnityEvent.value = `selectDevice:${deviceCode}`
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '设备视角切换失败')
  }
}

async function focusSelectedDevice() {
  try {
    await sendTrackedUnityCommand(
      'FOCUS_DEVICE',
      'Unity 视角聚焦当前设备',
      'focusDevice',
      { deviceCode: selectedDeviceCode.value },
    )
    lastUnityEvent.value = `focusDevice:${selectedDeviceCode.value}`
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '视角重新居中失败')
  }
}

async function switchCamera(mode: string) {
  try {
    await sendTrackedUnityCommand('SWITCH_CAMERA', 'Unity 切换态势观察视角', 'switchCamera', { mode })
    selectedCameraMode.value = mode
    lastUnityEvent.value = `switchCamera:${mode}`
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'Unity 视角切换失败')
  }
}

async function toggleUnityTrajectory() {
  if (!unityBridgeStore.connected || unityBridgeStore.trajectoryTogglePending) return
  const visible = !unityBridgeStore.trajectoryVisible
  unityBridgeStore.setTrajectoryTogglePending(true)
  try {
    const result = await recordRuntimeCommand(
      'TOGGLE_TRAJECTORY',
      visible ? 'Unity 显示现有轨迹' : 'Unity 隐藏现有轨迹',
      '',
      { visible },
    )
    unityBridgeStore.send('toggleTrajectory', { visible }, result.commandKey)
    lastUnityEvent.value = `toggleTrajectory:${visible ? 'show' : 'hide'}`
    if (trajectoryToggleTimer !== null) window.clearTimeout(trajectoryToggleTimer)
    trajectoryToggleTimer = window.setTimeout(() => {
      trajectoryToggleTimer = null
      if (!unityBridgeStore.trajectoryTogglePending) return
      unityBridgeStore.setTrajectoryTogglePending(false)
      ElMessage.error('Unity 轨迹显示指令未返回确认')
    }, 6000)
  } catch {
    unityBridgeStore.setTrajectoryTogglePending(false)
  }
}

function unityBridgeCommand(commandType: RuntimeCommandType) {
  const commands: Partial<Record<RuntimeCommandType, string>> = {
    UAV_TAKEOFF: 'uavTakeoff',
    UAV_HOVER: 'uavHover',
    UAV_RESUME: 'uavResume',
    UAV_RETURN: 'uavReturn',
    UAV_LAND: 'uavLand',
    UAV_EMERGENCY_LAND: 'uavEmergencyLand',
    USV_DEPART: 'usvDepart',
    USV_HOLD: 'usvHold',
    USV_RESUME: 'usvResume',
    USV_RETURN: 'usvReturn',
    USV_STOP: 'usvStop',
    USV_EMERGENCY_STOP: 'usvEmergencyStop',
  }
  return commands[commandType] ?? commandType.toLowerCase()
}

type VehicleBatchResult = {
  total: number
  acknowledged: number
  failed: number
  allAcknowledged: boolean
}

async function sendVehicleCommand(
  command: VehicleQuickCommand,
  options: { manageBusy?: boolean; notify?: boolean } = {},
): Promise<VehicleBatchResult> {
  const manageBusy = options.manageBusy ?? true
  const notify = options.notify ?? true
  if (!command.deviceCodes.length) {
    return { total: 0, acknowledged: 0, failed: 0, allAcknowledged: false }
  }
  if (!unityBridgeStore.connected || !trajectoryLive.value) {
    const feedback = { ...commandFeedback.value }
    for (const deviceCode of command.deviceCodes) feedback[normalizeDeviceCode(deviceCode)] = 'FAILED'
    commandFeedback.value = feedback
    if (notify) ElMessage.error(`${command.label}：${unityBridgeStore.connected ? 'Unity 实时遥测已中断' : 'Unity WebGL 尚未连接'}，未创建后端控制指令`)
    return {
      total: command.deviceCodes.length,
      acknowledged: 0,
      failed: command.deviceCodes.length,
      allAcknowledged: false,
    }
  }
  if (manageBusy) commandBusy.value = true
  const bridgeCommand = unityBridgeCommand(command.commandType)
  try {
    const statuses: RuntimeCommandStatus[] = []
    // Unity WebGL exposes a single command bridge. Keep the request/ACK pairs
    // ordered so a six-device deployment cannot lose one three-device group.
    for (const deviceCode of command.deviceCodes) {
      const status = await (async (): Promise<RuntimeCommandStatus> => {
        const key = normalizeDeviceCode(deviceCode)
        commandFeedback.value = { ...commandFeedback.value, [key]: 'PENDING' }
        try {
          const result = await recordRuntimeCommand(
            command.commandType,
            `${command.label} / ${deviceCode}`,
            key,
            { action: bridgeCommand },
          )
          if (result.status === 'FAILED' || result.status === 'TIMEOUT') {
            commandFeedback.value = { ...commandFeedback.value, [key]: result.status }
            return result.status
          }
          if (!unityBridgeStore.connected) throw new Error('Unity WebGL 尚未连接')

          const acknowledgement = await unityBridgeStore.sendControlCommandAndWait(
            bridgeCommand,
            key,
            result.commandKey,
          )
          const status: RuntimeCommandStatus = acknowledgement.success ? 'ACKNOWLEDGED' : 'FAILED'
          commandFeedback.value = { ...commandFeedback.value, [key]: status }
          if (acknowledgement.success) {
            const reportedState = normalizeOperationalState(
              acknowledgement.status.split(':', 1)[0]?.trim(),
              key.startsWith('uav') ? 'UAV' : 'USV',
            )
            const state = reportedState || operationalStateAfterCommand(command.commandType)
            if (state) operationalStates.value = { ...operationalStates.value, [key]: state }
          }
          return status
        } catch (error) {
          const status: RuntimeCommandStatus = error instanceof Error && error.message.includes('超时') ? 'TIMEOUT' : 'FAILED'
          commandFeedback.value = { ...commandFeedback.value, [key]: status }
          return status
        }
      })()
      statuses.push(status)
    }
    const acknowledged = statuses.filter((status) => status === 'ACKNOWLEDGED').length
    const failed = statuses.length - acknowledged
    const result = {
      total: statuses.length,
      acknowledged,
      failed,
      allAcknowledged: statuses.length > 0 && acknowledged === statuses.length,
    }
    lastUnityEvent.value = `vehicle-command:${bridgeCommand}`
    unityCommandState.value = `${command.label}：${acknowledged}/${statuses.length} 已确认`
    if (notify) {
      if (result.allAcknowledged) ElMessage.success(`${command.label}：${acknowledged}/${statuses.length} 台已确认`)
      else ElMessage.error(`${command.label}：成功 ${acknowledged}，失败 ${failed}`)
    }
    return result
  } finally {
    if (manageBusy) commandBusy.value = false
  }
}

async function sendFleetPair(
  uavCommand: VehicleQuickCommand['commandType'],
  uavLabel: string,
  usvCommand: VehicleQuickCommand['commandType'],
  usvLabel: string,
) {
  const uav = await sendOverviewFleetCommand('UAV', uavCommand, uavLabel)
  const usv = await sendOverviewFleetCommand('USV', usvCommand, usvLabel)
  return {
    total: uav.total + usv.total,
    acknowledged: uav.acknowledged + usv.acknowledged,
    failed: uav.failed + usv.failed,
    allAcknowledged: uav.allAcknowledged && usv.allAcknowledged,
  }
}

async function sendOverviewFleetCommand(
  vehicleType: 'UAV' | 'USV',
  commandType: VehicleQuickCommand['commandType'],
  label: string,
): Promise<VehicleBatchResult> {
  const allowedStates: Partial<Record<VehicleQuickCommand['commandType'], string[]>> = {
    UAV_TAKEOFF: ['GROUNDED'], UAV_HOVER: ['AIRBORNE', 'RETURNING'], UAV_RESUME: ['HOLDING'],
    UAV_RETURN: ['AIRBORNE', 'HOLDING'], UAV_LAND: ['AIRBORNE', 'HOLDING', 'RETURNING'],
    USV_DEPART: ['MOORED', 'STOPPED'], USV_HOLD: ['SAILING', 'RETURNING'], USV_RESUME: ['HOLDING'],
    USV_RETURN: ['SAILING', 'HOLDING'], USV_STOP: ['SAILING', 'HOLDING', 'RETURNING'],
  }
  const desiredStates: Partial<Record<VehicleQuickCommand['commandType'], string[]>> = {
    UAV_TAKEOFF: ['TAKING_OFF', 'AIRBORNE', 'HOLDING'], UAV_HOVER: ['HOLDING'], UAV_RESUME: ['AIRBORNE'],
    UAV_RETURN: ['RETURNING'], UAV_LAND: ['LANDING', 'GROUNDED'],
    USV_DEPART: ['DEPARTING', 'SAILING', 'HOLDING'], USV_HOLD: ['HOLDING'], USV_RESUME: ['SAILING'],
    USV_RETURN: ['RETURNING'], USV_STOP: ['STOPPED', 'MOORED'],
  }
  const devices = quickControlDevices.value.filter((device) => device.type === vehicleType)
  const isDeploymentCommand = commandType === 'UAV_TAKEOFF' || commandType === 'USV_DEPART'
  const eligible: string[] = []
  let alreadySatisfied = 0
  let invalid = 0
  for (const device of devices) {
    const state = normalizeOperationalState(operationalStates.value[normalizeDeviceCode(device.code)], vehicleType)
    if ((desiredStates[commandType] ?? []).includes(state)) alreadySatisfied += 1
    else if (isDeploymentCommand || (allowedStates[commandType] ?? []).includes(state)) eligible.push(device.code)
    else invalid += 1
  }
  if (invalid > 0) return { total: devices.length, acknowledged: alreadySatisfied, failed: invalid, allAcknowledged: false }
  if (!eligible.length) {
    return {
      total: devices.length,
      acknowledged: alreadySatisfied,
      failed: 0,
      allAcknowledged: devices.length > 0 && alreadySatisfied === devices.length,
    }
  }
  const issued = await sendVehicleCommand(
    { commandType, deviceCodes: eligible, label },
    { manageBusy: false, notify: false },
  )
  return {
    total: devices.length,
    acknowledged: alreadySatisfied + issued.acknowledged,
    failed: invalid + issued.failed,
    allAcknowledged: alreadySatisfied + issued.acknowledged === devices.length && issued.failed === 0,
  }
}

async function confirmReturn(action: 'return' | 'abort') {
  const abort = action === 'abort'
  await ElMessageBox.confirm(
    abort
      ? '终止任务后，将向全部无人机和无人艇下发返航指令。是否继续？'
      : '将向全部无人机和无人艇下发返航，并在确认后结束当前任务。是否继续？',
    abort ? '终止任务' : '全体返航',
    {
      confirmButtonText: abort ? '确认终止并返航' : '确认全体返航',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'mission-confirm-message-box',
      center: true,
      closeOnClickModal: false,
      closeOnPressEscape: false,
      distinguishCancelAndClose: true,
    },
  )
}

async function runOverviewDemoCommand(action: 'start' | 'pause' | 'resume' | 'cancel') {
  const commandType: Record<typeof action, RuntimeCommandType> = {
    start: 'START_MISSION',
    pause: 'PAUSE_MISSION',
    resume: 'RESUME_MISSION',
    cancel: 'CANCEL_MISSION',
  }
  const result = await recordRuntimeCommand(
    commandType[action],
    `系统总览独立演示：${action}`,
    '',
    { demo: true },
  )
  const acknowledgement = await unityBridgeStore.sendControlCommandAndWait(
    missionUnityCommand(action),
    '',
    result.commandKey,
  )
  if (!acknowledgement.success) throw new Error(acknowledgement.status || '系统总览 Unity 未确认演示指令')
  overviewMissionStatus.value = {
    start: 'RUNNING',
    pause: 'PAUSED',
    resume: 'RUNNING',
    cancel: 'CANCELLED',
  }[action] as MissionStatus
}

async function handleMissionGroupAction(action: 'deploy' | 'start' | 'pause' | 'resume' | 'return' | 'abort') {
  if (commandBusy.value) return
  if (!trajectoryLive.value) {
    ElMessage.error('Unity 实时遥测已中断，任务指令未下发')
    return
  }
  if (action === 'return' || action === 'abort') {
    try {
      await confirmReturn(action)
    } catch {
      return
    }
  }

  commandBusy.value = true
  try {
    if (action === 'abort') {
      await runOverviewDemoCommand('cancel')
      overviewDeploymentAcknowledged.value = false
      ElMessage.success('简单围捕任务已终止')
      return
    }

    if (action === 'deploy') {
      if (overviewMissionStatus.value === 'RUNNING' || overviewMissionStatus.value === 'PAUSED') {
        ElMessage.success('编组已经部署并处于任务状态，无需重复部署')
        return
      }
      // 这里只建立总览页自己的简单围捕编组。设备运动由后续
      // “开始任务”统一触发，避免逐台命令依赖 Unity 当前设备选择。
      overviewMissionStatus.value = 'READY'
      overviewDeploymentAcknowledged.value = true
      ElMessage.success(`编组部署完成：${quickControlDevices.value.length}/${quickControlDevices.value.length} 台载具已加入简单围捕`)
      return
    }

    if (action === 'start') {
      if (!overviewDeploymentAcknowledged.value) {
        throw new Error('请先点击“编组部署”，确认三机三艇加入围捕编组')
      }
      await runOverviewDemoCommand('start')
      ElMessage.success('简单围捕任务已启动')
      return
    }

    if (action === 'pause') {
      const held = await sendFleetPair('UAV_HOVER', '无人机编组悬停', 'USV_HOLD', '无人艇编组定点保持')
      if (!held.allAcknowledged) throw new Error(`暂停失败：${held.failed} 台载具未确认保持`)
      await runOverviewDemoCommand('pause')
      ElMessage.success('任务已暂停，三机三艇均已进入保持状态')
      return
    }

    if (action === 'resume') {
      const resumed = await sendFleetPair('UAV_RESUME', '无人机继续任务', 'USV_RESUME', '无人艇继续航行')
      if (!resumed.allAcknowledged) throw new Error(`继续任务失败：${resumed.failed} 台载具未确认恢复`)
      await runOverviewDemoCommand('resume')
      ElMessage.success('任务已继续，Unity 与后端状态均已确认')
      return
    }

    const returning = await sendFleetPair('UAV_RETURN', '无人机编组返航', 'USV_RETURN', '无人艇编组返航')
    if (!returning.allAcknowledged) throw new Error(`返航失败：${returning.failed} 台载具未确认返航`)
    await runOverviewDemoCommand('cancel')
    ElMessage.success('全体返航已确认，当前任务已结束')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务编组操作失败')
  } finally {
    commandBusy.value = false
  }
}

function handleUnityCommand(message: UnityMessage) {
  lastUnityEvent.value = `vue->unity:${message.type}`
  unityCommandState.value = `已发送：${message.type}`
}

function handleUnityReady() {
  unityConnection.value = 'Unity WebGL 已连接'
  lastUnityEvent.value = 'sceneLoaded'
  pushPoseFrameToUnity()
  // Unity 的“重新居中/当前设备视角”依赖内部已选中设备。
  // 首次连接时主动同步默认设备，避免出现 No Unity device is currently selected。
  unityBridgeStore.send('selectDevice', { deviceCode: selectedDeviceCode.value })
  startUnityHeartbeat()
}

function handleUnityMessage(message: UnityMessage) {
  const payload = message.payload ?? {}
  unityConnection.value = payload.source === 'mock' ? 'Unity Mock 已接入' : 'Unity WebGL 已连接'
  lastUnityEvent.value = message.type

  if (message.type === 'vueCommandReceived') {
    const commandType = String(payload.type ?? 'unknown')
    const bridgeSent = payload.bridgeSent === true ? '已送达 Unity' : '等待 Unity 实例'
    unityCommandState.value = `已接收：${commandType} / ${bridgeSent}`
  }

  if (message.type === 'commandAck') {
    const commandType = String(payload.commandType ?? 'unknown')
    const status = String(payload.status ?? 'unknown')
    const success = payload.success === true
    const deviceCode = normalizeDeviceCode(String(payload.deviceCode ?? ''))
    if (deviceCode) {
      commandFeedback.value = {
        ...commandFeedback.value,
        [deviceCode]: success ? 'ACKNOWLEDGED' : 'FAILED',
      }
      if (success) {
        const unityState = normalizeOperationalState(
          status.split(':', 1)[0]?.trim(),
          deviceCode.startsWith('uav') ? 'UAV' : 'USV',
        )
        if (unityState) operationalStates.value = { ...operationalStates.value, [deviceCode]: unityState }
      }
    } else if (success) {
      const missionState = status.split(':', 1)[0]?.trim().toUpperCase()
      if (['RUNNING', 'PAUSED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(missionState ?? '')) {
        overviewMissionStatus.value = missionState as MissionStatus
      }
    }
    unityCommandState.value = `${success ? '已执行' : '执行失败'}：${commandType} / ${status}`
  }

  if (message.type === 'cameraChanged') {
    const success = payload.success === true
    const status = String(payload.status ?? (success ? '视角切换完成' : '视角切换失败'))
    unityCommandState.value = `${success ? '已切换' : '切换失败'}：${status}`
    if (!success) ElMessage.error(status)
  }

  if (message.type === 'trajectoryVisibilityChanged') {
    const success = payload.success === true
    const visible = payload.visible !== false
    const status = String(payload.status ?? (visible ? 'Unity 轨迹已显示' : 'Unity 轨迹已隐藏'))
    if (trajectoryToggleTimer !== null) {
      window.clearTimeout(trajectoryToggleTimer)
      trajectoryToggleTimer = null
    }
    unityBridgeStore.setTrajectoryTogglePending(false)
    if (success) unityBridgeStore.setTrajectoryVisibility(visible)
    else ElMessage.error(status)
    unityCommandState.value = `${success ? '已执行' : '执行失败'}：${status}`
  }

  if (message.type !== 'cameraChanged' || payload.success === true) {
    if (typeof payload.deviceCode === 'string' && payload.deviceCode.trim()) selectedDeviceCode.value = payload.deviceCode
    if (typeof payload.mode === 'string' && payload.mode.trim()) selectedCameraMode.value = payload.mode
  }
}

function handleUnityError(message: string) {
  unityConnection.value = 'Unity WebGL 加载失败'
  lastUnityEvent.value = 'unityError'
  ElMessage.error(message)
  void sendUnityHeartbeat('FAILED')
}

onMounted(() => {
  unityViewportStore.show('dashboard')
  freshnessTimer = window.setInterval(() => { freshnessClock.value = Date.now() }, 500)
  void monitoringStore.refresh({}, true).then(pushPoseFrameToUnity)
  monitoringStore.connectEvents()
})

onActivated(() => unityViewportStore.show('dashboard'))
onDeactivated(() => {
  if (unityViewportStore.target === 'dashboard') unityViewportStore.park()
})

onBeforeUnmount(() => {
  if (unityViewportStore.target === 'dashboard') unityViewportStore.park()
  if (freshnessTimer !== null) window.clearInterval(freshnessTimer)
  if (trajectoryToggleTimer !== null) window.clearTimeout(trajectoryToggleTimer)
  stopUnityHeartbeat()
  monitoringStore.disconnectEvents()
})

watch(
  () =>
    monitoringStore.nodes
      .map(
        (node) =>
          `${node.code}:${node.status}:${node.positionX ?? '-'}:${node.positionY ?? '-'}:${node.positionZ ?? '-'}:${node.heartbeatAgeSeconds}`,
      )
      .join('|'),
  () => pushPoseFrameToUnity(),
)

watch(
  () => unityBridgeStore.connected,
  (connected) => {
    if (connected) handleUnityReady()
    else if (!unityBridgeStore.error) unityConnection.value = '等待 WebGL 构建'
  },
  { immediate: true },
)

watch(
  () => unityBridgeStore.lastMessage,
  (message) => {
    if (message) handleUnityMessage(message)
  },
)

watch(
  () => unityBridgeStore.lastOutgoing,
  (message) => {
    if (message) handleUnityCommand(message)
  },
)

watch(
  () => unityBridgeStore.error,
  (message) => {
    if (message) handleUnityError(message)
  },
)

function syncOperationalStatesFromTrajectory() {
  const frame = trajectoryStore.frame
  if (!frame?.agents?.length) return

  const next = { ...operationalStates.value }
  for (const agent of frame.agents) {
    if (agent.type !== 'UAV' && agent.type !== 'USV') continue
    next[normalizeDeviceCode(agent.code)] = normalizeOperationalState(agent.state, agent.type)
  }
  operationalStates.value = next
}

watch(
  () => trajectoryStore.frame?.sequence,
  () => syncOperationalStatesFromTrajectory(),
)
</script>

<template>
  <ConsoleLayout title="系统总览" eyebrow="MISSION OVERVIEW">
    <section class="overview-console overview-hf" aria-label="海空协同仿真总览">
      <header class="overview-hf-statusbar">
        <div class="overview-current-view">
          <span>{{ selectedDeviceCode.toUpperCase() }}</span>
          <strong>当前观察设备</strong>
          <small>{{ selectedCameraMode === 'device-follow' ? '设备跟随视角' : cameraModes.find((item) => item.value === selectedCameraMode)?.label }}</small>
        </div>
        <div class="overview-link-status">
          <b :class="{ online: rosBridgeOnline }"><i></i>ROS {{ rosBridgeOnline ? '在线' : '离线' }}</b>
          <b :class="{ online: unityReady }"><i></i>Unity {{ unityReady ? '在线' : '等待' }}</b>
          <b class="pose"><i></i>{{ realtimePoseCount }}/6 位姿</b>
          <b><i></i>{{ onlineNodeCount }}/{{ displayedNodes.length }} 节点</b>
        </div>
      </header>

      <div class="overview-main-grid overview-hf-main">
        <section class="overview-stage-panel">
          <div class="overview-stage-header">
            <div>
              <h3>Unity 海空协同态势</h3>
              <span>当前任务：{{ overviewMissionName }} · {{ taskStateText }}</span>
            </div>
            <div class="overview-camera-tabs" aria-label="Unity 视角切换">
              <button
                v-for="mode in cameraModes"
                :key="mode.value"
                type="button"
                :class="{ active: selectedCameraMode === mode.value }"
                :disabled="cameraCommandBusy || !unityBridgeStore.connected"
                @click="switchCamera(mode.value)"
              >
                {{ mode.label }}
              </button>
              <button
                type="button"
                :class="{ active: !unityBridgeStore.trajectoryVisible }"
                :disabled="!unityBridgeStore.connected || unityBridgeStore.trajectoryTogglePending"
                :aria-pressed="!unityBridgeStore.trajectoryVisible"
                @click="toggleUnityTrajectory"
              >
                {{ unityBridgeStore.trajectoryVisible ? '隐藏轨迹' : '显示轨迹' }}
              </button>
            </div>
            <button class="overview-tool-button" type="button" :disabled="cameraCommandBusy || !unityBridgeStore.connected" @click="focusSelectedDevice">重新居中</button>
          </div>

          <div class="overview-unity-stage unity-runtime-viewport" data-unity-runtime-viewport="dashboard">
            <div v-if="!unityBridgeStore.connected" class="unity-runtime-placeholder">
              <strong>Unity WebGL 常驻实例启动中</strong>
              <span>{{ unityBridgeStore.error || '正在加载全局运行实例，请稍候' }}</span>
            </div>
          </div>
        </section>

        <aside class="overview-ops-panel">
          <div class="overview-control-stack">
            <UnifiedVehicleControl
              :devices="selectableDevices"
              :selected-device-code="selectedDeviceCode"
              :feedback="commandFeedback"
              :operational-states="operationalStates"
              :busy="commandBusy || !trajectoryLive"
              @select="selectDevice"
              @command="sendVehicleCommand"
            />
            <MissionGroupControl
              :mission-name="overviewMissionName"
              :status="overviewMissionStatus"
              :busy="commandBusy || !trajectoryLive"
              :progress="missionGroupProgress"
              :can-deploy="!['RUNNING', 'PAUSED'].includes(overviewMissionStatus)"
              :can-start="overviewMissionStatus === 'READY' && overviewDeploymentAcknowledged"
              :readiness-text="missionReadinessText"
              @action="handleMissionGroupAction"
            />
          </div>
        </aside>
      </div>

      <section class="overview-fleet-ribbon" aria-label="六载具实时状态">
        <article
          v-for="device in overviewFleetCards"
          :key="device.code"
          :class="[device.type.toLowerCase(), { active: normalizeDeviceCode(selectedDeviceCode) === device.code }]"
          @click="selectDevice(device.code)"
        >
          <header>
            <strong>{{ device.code.toUpperCase() }}</strong>
            <b :class="device.feedback?.toLowerCase()">{{ device.feedback === 'ACKNOWLEDGED' ? '已确认' : device.status }}</b>
          </header>
          <VehicleGlyph
            class="overview-fleet-symbol"
            :type="device.type === 'UAV' ? 'UAV' : 'USV'"
            size="large"
            :active="normalizeDeviceCode(selectedDeviceCode) === device.code"
          />
          <span>{{ device.stateLabel }}</span>
          <footer>
            <small>位姿 {{ device.positionX === null ? '--' : '实时' }}</small>
            <small>电量 --</small>
          </footer>
        </article>
      </section>

    </section>
  </ConsoleLayout>
</template>
