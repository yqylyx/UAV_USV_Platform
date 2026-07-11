<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionGroupControl from '@/components/control/MissionGroupControl.vue'
import VehicleQuickControl from '@/components/control/VehicleQuickControl.vue'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import { sendIntegrationHeartbeat } from '@/api/integration'
import { issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'
import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'
import { useMonitoringStore } from '@/stores/monitoring'
import type { RuntimeNode } from '@/types/monitoring'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

type UnityPanelExpose = {
  selectDevice: (deviceCode: string) => void
  focusDevice: (deviceCode: string) => void
  switchCamera: (mode: string) => void
  sendControlCommand: (command: string, deviceCode?: string) => void
  sendPoseFrame: (payload: Record<string, unknown>) => void
}

const monitoringStore = useMonitoringStore()
const unityPanel = ref<UnityPanelExpose | null>(null)
const selectedDeviceCode = ref('uav-01')
const selectedCameraMode = ref('overview')
const unityConnection = ref('等待 WebGL 构建')
const lastUnityEvent = ref('暂无 Unity 回传事件')
const unityCommandState = ref('等待控制指令')
const commandBusy = ref(false)
const commandFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
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

function formatCoordinate(value: number | null) {
  return value === null ? '-' : value.toFixed(2)
}

function formatHeartbeat(age: number) {
  if (age < 0) return '-'
  if (age < 60) return `${age}s`
  return `${Math.floor(age / 60)}m ${age % 60}s`
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
const topStatusCards = computed(() => [
  {
    label: 'ROS / Gazebo',
    value: rosBridgeOnline.value ? '在线' : '离线',
    tone: rosBridgeOnline.value ? 'online' : 'offline',
    detail: rosBridgeOnline.value ? 'WebSocket 数据链路可用' : '等待 ROS bridge 心跳',
  },
  {
    label: 'Unity WebGL',
    value: unityReady.value ? '在线' : '等待',
    tone: unityReady.value ? 'online' : 'warning',
    detail: unityConnection.value,
  },
  {
    label: '位姿同步',
    value: `${realtimePoseCount.value}/6`,
    tone: realtimePoseCount.value >= 6 ? 'online' : 'warning',
    detail: realtimePoseCount.value > 0 ? `已同步 ${realtimePoseCount.value} 个载体` : '尚未收到实时位姿',
  },
  {
    label: '最新命令',
    value: unityCommandState.value.includes('失败') ? '异常' : '就绪',
    tone: unityCommandState.value.includes('失败') ? 'offline' : 'online',
    detail: unityCommandState.value,
  },
])

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

  unityPanel.value?.sendPoseFrame({
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
  unityPanel.value?.selectDevice(deviceCode)
  lastUnityEvent.value = `selectDevice:${deviceCode}`
  void recordRuntimeCommand('SELECT_DEVICE', '系统总览选择协同设备', deviceCode).catch(() => undefined)
}

async function focusSelectedDevice() {
  unityPanel.value?.focusDevice(selectedDeviceCode.value)
  lastUnityEvent.value = `focusDevice:${selectedDeviceCode.value}`
  void recordRuntimeCommand('FOCUS_DEVICE', 'Unity 视角聚焦当前设备').catch(() => undefined)
}

async function switchCamera(mode: string) {
  selectedCameraMode.value = mode
  unityPanel.value?.switchCamera(mode)
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
  try {
    const results = await Promise.all(
      command.deviceCodes.map(async (deviceCode) => {
        const key = normalizeDeviceCode(deviceCode)
        commandFeedback.value = { ...commandFeedback.value, [key]: 'PENDING' }
        const result = await recordRuntimeCommand(
          command.commandType,
          `${command.label} / ${deviceCode}`,
          key,
          { action: bridgeCommand },
        )
        commandFeedback.value = { ...commandFeedback.value, [key]: result.status }
        unityPanel.value?.sendControlCommand(bridgeCommand, key)
        return result
      }),
    )
    lastUnityEvent.value = `vehicle-command:${bridgeCommand}`
    unityCommandState.value = `${command.label}：${results.filter((item) => item.status === 'ACKNOWLEDGED').length}/${results.length} 已确认`
    ElMessage.success(`${command.label}已下发至 ${command.deviceCodes.length} 台设备`)
  } catch (error) {
    command.deviceCodes.forEach((deviceCode) => {
      commandFeedback.value = { ...commandFeedback.value, [normalizeDeviceCode(deviceCode)]: 'FAILED' }
    })
    ElMessage.error(error instanceof Error ? error.message : `${command.label}下发失败`)
  } finally {
    commandBusy.value = false
  }
}

async function handleMissionGroupAction(action: 'deploy' | 'start' | 'pause' | 'resume' | 'return' | 'abort') {
  if (action === 'deploy') {
    await sendVehicleCommand({ commandType: 'UAV_TAKEOFF', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机编组起飞' })
    await sendVehicleCommand({ commandType: 'USV_DEPART', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇编组离泊' })
    return
  }
  if (action === 'return') {
    await sendVehicleCommand({ commandType: 'UAV_RETURN', deviceCodes: ['uav-01', 'uav-02', 'uav-03'], label: '无人机编组返航' })
    await sendVehicleCommand({ commandType: 'USV_RETURN', deviceCodes: ['usv-01', 'usv-02', 'usv-03'], label: '无人艇编组返航' })
    return
  }
  const commandMap: Record<Exclude<typeof action, 'deploy' | 'return'>, RuntimeCommandType> = {
    start: 'START_MISSION',
    pause: 'PAUSE_MISSION',
    resume: 'RESUME_MISSION',
    abort: 'FAIL_MISSION',
  }
  commandBusy.value = true
  try {
    const result = await recordRuntimeCommand(commandMap[action], `系统总览任务编组操作：${action}`, '', { action })
    unityCommandState.value = `任务指令：${result.status}`
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
</script>

<template>
  <ConsoleLayout title="系统总览" eyebrow="MISSION OVERVIEW">
    <section class="overview-console" aria-label="海空协同仿真总览">
      <div class="overview-status-strip">
        <article v-for="card in topStatusCards" :key="card.label" class="overview-status-card" :class="card.tone">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.detail }}</small>
        </article>
      </div>

      <div class="overview-main-grid">
        <div class="overview-left-col">
        <section class="overview-stage-panel">
          <div class="overview-stage-header">
            <div>
              <h3>Unity 三维态势</h3>
              <span>当前任务：{{ taskStateText }}</span>
            </div>
            <div class="overview-stage-signals">
              <b :class="{ online: rosBridgeOnline }">ROS2 WebSocket</b>
              <b :class="{ online: rosBridgeOnline }">Unity WebGL</b>
            </div>
          </div>

          <div class="overview-toolbar">
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

          <UnityWebglPanel
            ref="unityPanel"
            class="overview-unity-stage"
            @unity-ready="handleUnityReady"
            @unity-message="handleUnityMessage"
            @unity-error="handleUnityError"
            @unity-command="handleUnityCommand"
          />
        </section>

        <section class="overview-live-panel">
          <div class="overview-live-head">
          <h3>实时节点</h3>
          <span>状态由 ROS WebSocket 数据和 Unity 心跳共同确认。</span>
          </div>
          <div class="overview-node-table">
          <div class="overview-node-row head">
            <span>节点</span>
            <span>类型</span>
            <span>状态</span>
            <span>坐标 X/Y/Z</span>
            <span>心跳</span>
          </div>
          <div v-for="node in displayedNodes" :key="node.code" class="overview-node-row">
            <strong>{{ node.code }}</strong>
            <span>{{ node.type }}</span>
            <b :class="node.status.toLowerCase()">{{ node.status }}</b>
            <span>{{ formatCoordinate(node.positionX) }} / {{ formatCoordinate(node.positionY) }} / {{ formatCoordinate(node.positionZ) }}</span>
            <span>{{ formatHeartbeat(node.heartbeatAgeSeconds) }}</span>
          </div>
          <div v-if="displayedNodes.length === 0" class="overview-empty-row">暂无实时节点数据</div>
        </div>
        </section>
        </div>

        <aside class="overview-ops-panel">
          <div class="overview-runtime-summary">
          <strong>{{ onlineNodeCount }} / {{ displayedNodes.length }}</strong>
          <span>实时节点在线</span>
        </div>

          <section>
            <h3>任务与控制</h3>
            <div class="overview-info-stack">
              <div>
                <span>任务状态</span>
                <strong>{{ taskStateText }}</strong>
              </div>
              <div>
                <span>Unity 通信</span>
                <strong>{{ unityConnection }}</strong>
                <small>{{ lastUnityEvent }}</small>
              </div>
              <div>
                <span>命令状态</span>
                <strong>{{ unityCommandState }}</strong>
              </div>
            </div>
          </section>
          <div class="overview-control-stack">
            <VehicleQuickControl
              vehicle-type="UAV"
              :devices="quickControlDevices"
              :selected-device-code="selectedDeviceCode"
              :feedback="commandFeedback"
              :busy="commandBusy"
              compact
              @select="selectDevice"
              @command="sendVehicleCommand"
            />
            <VehicleQuickControl
              vehicle-type="USV"
              :devices="quickControlDevices"
              :selected-device-code="selectedDeviceCode"
              :feedback="commandFeedback"
              :busy="commandBusy"
              compact
              @select="selectDevice"
              @command="sendVehicleCommand"
            />
            <MissionGroupControl
              mission-name="三机三艇协同围捕"
              :status="taskStateText === '实时同步' ? 'RUNNING' : 'READY'"
              :busy="commandBusy"
              :progress="realtimePoseCount === 6 ? 72 : 18"
              @action="handleMissionGroupAction"
            />
          </div>
        </aside>
      </div>

  </section>
  </ConsoleLayout>
</template>
