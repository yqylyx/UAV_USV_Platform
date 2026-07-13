<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionGroupControl from '@/components/control/MissionGroupControl.vue'
import VehicleQuickControl from '@/components/control/VehicleQuickControl.vue'
import VehicleGlyph from '@/components/control/VehicleGlyph.vue'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import { sendIntegrationHeartbeat } from '@/api/integration'
import { issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'
import { useMonitoringStore } from '@/stores/monitoring'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import type { RuntimeNode } from '@/types/monitoring'
import { normalizeOperationalState } from '@/utils/runtimeOperationalState'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

const monitoringStore = useMonitoringStore()
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
const selectedDeviceCode = ref('uav-01')
const selectedCameraMode = ref('overview')
const unityConnection = ref('等待 WebGL 构建')
const lastUnityEvent = ref('暂无 Unity 回传事件')
const unityCommandState = ref('等待控制指令')
const commandBusy = ref(false)
const commandFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
const operationalStates = ref<Record<string, string | undefined>>({
  'uav-01': 'GROUNDED',
  'uav-02': 'GROUNDED',
  'uav-03': 'GROUNDED',
  'usv-01': 'MOORED',
  'usv-02': 'MOORED',
  'usv-03': 'MOORED',
})
type OverviewMissionStatus = 'READY' | 'RUNNING' | 'PAUSED' | 'FAILED' | 'CANCELLED' | 'COMPLETED'
const overviewMissionStatus = ref<OverviewMissionStatus>('READY')
let poseFrameSequence = 0
let heartbeatTimer: number | null = null
const unityInstanceId = `vue-webgl:${window.location.host}:${Math.random().toString(36).slice(2, 10)}`

const cameraModes = [
  { label: '总览', value: 'overview' },
  { label: '当前设备', value: 'device-follow' },
  { label: '行动视角', value: 'action' },
  { label: '灯塔视角', value: 'lighthouse' },
]

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

const quickControlDevices = computed(() =>
  selectableDevices.value.map((device) => ({
    code: device.code,
    name: device.name,
    type: device.type as 'UAV' | 'USV',
    status: device.status,
  })),
)

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
const fleetReady = computed(() =>
  Object.entries(operationalStates.value).every(([code, state]) =>
    code.startsWith('uav')
      ? ['AIRBORNE', 'HOLDING'].includes(normalizeOperationalState(state, 'UAV'))
      : ['SAILING', 'HOLDING'].includes(normalizeOperationalState(state, 'USV')),
  ),
)

const overviewFleetCards = computed(() =>
  selectableDevices.value.map((device, index) => {
    const code = normalizeDeviceCode(device.code)
    const state = normalizeOperationalState(operationalStates.value[code], device.type === 'UAV' ? 'UAV' : 'USV')
    const labels: Record<string, string> = {
      GROUNDED: '地面待命', AIRBORNE: '空中执行', HOLDING: '安全保持', RETURNING: '返航中', LANDING: '降落中',
      MOORED: '靠泊待命', SAILING: '航行中', STOPPED: '已停止', ERROR: '异常',
    }
    return {
      ...device,
      code,
      state,
      stateLabel: labels[state] ?? state,
      battery: device.type === 'UAV' ? 92 - index * 2 : 81 - index,
      link: Math.max(1, 19 - (index % 3)),
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
      payload: payload ? JSON.stringify(payload) : undefined,
      detail,
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '控制指令下发失败')
    throw error
  }
}

async function selectDevice(deviceCode: string) {
  selectedDeviceCode.value = deviceCode
  selectedCameraMode.value = 'device-follow'
  unityBridgeStore.send('selectDevice', { deviceCode })
  lastUnityEvent.value = `selectDevice:${deviceCode}`
  void recordRuntimeCommand('SELECT_DEVICE', '系统总览选择协同设备', deviceCode).catch(() => undefined)
}

async function focusSelectedDevice() {
  unityBridgeStore.send('focusDevice', { deviceCode: selectedDeviceCode.value })
  lastUnityEvent.value = `focusDevice:${selectedDeviceCode.value}`
  void recordRuntimeCommand('FOCUS_DEVICE', 'Unity 视角聚焦当前设备').catch(() => undefined)
}

async function switchCamera(mode: string) {
  selectedCameraMode.value = mode
  unityBridgeStore.send('switchCamera', { mode })
  lastUnityEvent.value = `switchCamera:${mode}`
  void recordRuntimeCommand('SWITCH_CAMERA', 'Unity 切换态势观察视角', selectedDeviceCode.value, { mode }).catch(() => undefined)
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

async function sendVehicleCommand(command: VehicleQuickCommand) {
  commandBusy.value = true
  const bridgeCommand = unityBridgeCommand(command.commandType)
  const statuses = await Promise.all(
      command.deviceCodes.map(async (deviceCode) => {
        const key = normalizeDeviceCode(deviceCode)
        commandFeedback.value = { ...commandFeedback.value, [key]: 'PENDING' }
        try {
          const result = await recordRuntimeCommand(
            command.commandType,
            `${command.label} / ${deviceCode}`,
            key,
            { action: bridgeCommand },
          )
          commandFeedback.value = { ...commandFeedback.value, [key]: result.status }
          if (result.status === 'ACKNOWLEDGED') {
            const state = operationalStateAfterCommand(command.commandType)
            if (state) operationalStates.value = { ...operationalStates.value, [key]: state }
          }
          unityBridgeStore.sendControlCommand(bridgeCommand, key, result.commandKey)
          return result.status
        } catch {
          commandFeedback.value = { ...commandFeedback.value, [key]: 'FAILED' }
          return 'FAILED' as RuntimeCommandStatus
        }
      }),
    )
  const acknowledged = statuses.filter((status) => status === 'ACKNOWLEDGED').length
  const failed = statuses.filter((status) => status === 'FAILED' || status === 'TIMEOUT').length
  lastUnityEvent.value = `vehicle-command:${bridgeCommand}`
  unityCommandState.value = `${command.label}：${acknowledged}/${statuses.length} 已确认`
  if (failed) ElMessage.error(`${command.label}：成功 ${acknowledged}，失败 ${failed}`)
  else ElMessage.success(`${command.label}已下发至 ${command.deviceCodes.length} 台设备`)
  commandBusy.value = false
  return failed === 0
}

async function handleMissionGroupAction(action: 'deploy' | 'start' | 'pause' | 'resume' | 'return' | 'abort') {
  if (action === 'deploy') {
    await Promise.all([
      sendVehicleCommand({ commandType: 'UAV_TAKEOFF', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机编组起飞' }),
      sendVehicleCommand({ commandType: 'USV_DEPART', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇编组离泊' }),
    ])
    return
  }
  if (action === 'return') {
    await Promise.all([
      sendVehicleCommand({ commandType: 'UAV_RETURN', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机编组返航' }),
      sendVehicleCommand({ commandType: 'USV_RETURN', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇编组返航' }),
    ])
    overviewMissionStatus.value = 'CANCELLED'
    return
  }

  if (action === 'abort') {
    try {
      await ElMessageBox.confirm(
        '终止任务后，将向全部无人机和无人艇下发返航指令。是否继续？',
        '终止任务',
        {
          confirmButtonText: '确认终止并返航',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      return
    }

    commandBusy.value = true

    try {
      const returned = await Promise.all([
        sendVehicleCommand({
          commandType: 'UAV_RETURN',
          deviceCodes: ['uav-01', 'uav-02', 'uav-03'],
          label: '无人机编组返航',
        }),
        sendVehicleCommand({
          commandType: 'USV_RETURN',
          deviceCodes: ['usv-01', 'usv-02', 'usv-03'],
          label: '无人艇编组返航',
        }),
      ])

      if (!returned.every(Boolean)) {
        ElMessage.error('部分载具未能接收返航指令')
        return
      }

      const result = await recordRuntimeCommand(
        'CANCEL_MISSION',
        '系统总览：终止任务并全体返航',
        '',
        { action: 'abort' },
      )

      if (
        result.status === 'DISPATCHED' ||
        result.status === 'PENDING'
      ) {
        unityBridgeStore.sendControlCommand(
          'missionCancel',
          '',
          result.commandKey,
        )
      }

      overviewMissionStatus.value = 'CANCELLED'
      ElMessage.success('任务已终止，全体载具正在返航')
    } finally {
      commandBusy.value = false
    }

    return
  }


  const commandMap: Record<Exclude<typeof action, 'deploy' | 'return'>, RuntimeCommandType> = {
    start: 'START_MISSION',
    pause: 'PAUSE_MISSION',
    resume: 'RESUME_MISSION',
  }
  commandBusy.value = true
  try {

    if (action === 'start' && !fleetReady.value) {
      ElMessage.warning('请先完成三机三艇编组部署')
      return
    }

    if (action === 'pause') {
      await Promise.all([
        sendVehicleCommand({ commandType: 'UAV_HOVER', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机编组悬停' }),
        sendVehicleCommand({ commandType: 'USV_HOLD', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇编组保持' }),
      ])
    }
    if (action === 'resume') {
      await Promise.all([
        sendVehicleCommand({ commandType: 'UAV_RESUME', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机继续任务' }),
        sendVehicleCommand({ commandType: 'USV_RESUME', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇继续航行' }),
      ])
    }
    const result = await recordRuntimeCommand(commandMap[action], `系统总览任务编组操作：${action}`, '', { action })
    if (result.status === 'DISPATCHED' || result.status === 'PENDING') {
      const unityActions = {
        deploy: 'missionResume',
        start: 'missionStart',
        pause: 'missionPause',
        resume: 'missionResume',
        return: 'missionReturn',
      } as const
      unityBridgeStore.sendControlCommand(unityActions[action], '', result.commandKey)
    }
    unityCommandState.value = `任务指令：${result.status}`
    if (result.status === 'ACKNOWLEDGED') {
      if (action === 'start' || action === 'resume') overviewMissionStatus.value = 'RUNNING'
      if (action === 'pause') overviewMissionStatus.value = 'PAUSED'
    }
    ElMessage.success('任务编组指令已记录')
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
        overviewMissionStatus.value = missionState as OverviewMissionStatus
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
  void monitoringStore.refresh({}, true).then(pushPoseFrameToUnity)
  monitoringStore.connectEvents()
})

onBeforeUnmount(() => {
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
              <span>当前任务：三机三艇协同围捕 · {{ taskStateText }}</span>
            </div>
            <div class="overview-camera-tabs" aria-label="Unity 视角切换">
              <button
                v-for="mode in cameraModes"
                :key="mode.value"
                type="button"
                :class="{ active: selectedCameraMode === mode.value }"
                @click="switchCamera(mode.value)"
              >
                {{ mode.label }}
              </button>
            </div>
            <button class="overview-tool-button" type="button" @click="focusSelectedDevice">重新居中</button>
          </div>

          <div class="overview-unity-stage unity-runtime-viewport" data-unity-runtime-viewport>
            <div v-if="!unityBridgeStore.connected" class="unity-runtime-placeholder">
              <strong>Unity WebGL 常驻实例启动中</strong>
              <span>{{ unityBridgeStore.error || '正在加载全局运行实例，请稍候' }}</span>
            </div>
          </div>
        </section>

        <aside class="overview-ops-panel">
          <div class="overview-control-stack">
            <VehicleQuickControl
              vehicle-type="UAV"
              :devices="quickControlDevices"
              :selected-device-code="selectedDeviceCode"
              :feedback="commandFeedback"
              :operational-states="operationalStates"
              :busy="commandBusy"
              @select="selectDevice"
              @command="sendVehicleCommand"
            />
            <VehicleQuickControl
              vehicle-type="USV"
              :devices="quickControlDevices"
              :selected-device-code="selectedDeviceCode"
              :feedback="commandFeedback"
              :operational-states="operationalStates"
              :busy="commandBusy"
              @select="selectDevice"
              @command="sendVehicleCommand"
            />
            <MissionGroupControl
              mission-name="三机三艇协同围捕"
              :status="overviewMissionStatus"
              :busy="commandBusy"
              :progress="realtimePoseCount === 6 ? 72 : 18"
              :can-deploy="overviewMissionStatus === 'READY' && !fleetReady"
              :can-start="overviewMissionStatus === 'READY' && fleetReady"
              :readiness-text="fleetReady ? '6/6 载具就绪' : '等待三机三艇部署'"
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
            <small>信号 {{ device.link }}</small>
            <small>电量 {{ device.battery }}%</small>
          </footer>
        </article>
      </section>

    </section>
  </ConsoleLayout>
</template>
