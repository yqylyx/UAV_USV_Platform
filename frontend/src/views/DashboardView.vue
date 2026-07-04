<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { sendIntegrationHeartbeat } from '@/api/integration'
import { issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandType } from '@/api/runtimeControl'
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
  toggleTrajectory: (visible: boolean) => void
  sendControlCommand: (command: string, deviceCode?: string) => void
  sendPoseFrame: (payload: Record<string, unknown>) => void
}

const monitoringStore = useMonitoringStore()
const unityPanel = ref<UnityPanelExpose | null>(null)
const selectedDeviceCode = ref('USV-01')
const selectedCameraMode = ref('overview')
const trajectoryVisible = ref(true)
const unityConnection = ref('等待 WebGL 构建')
const lastUnityEvent = ref('暂无 Unity 回传事件')
const unityCommandState = ref('等待控制指令')
let poseFrameSequence = 0
let heartbeatTimer: number | null = null
const unityInstanceId = `vue-webgl:${window.location.host}:${Math.random().toString(36).slice(2, 10)}`

const cameraModes = [
  { label: '总览', value: 'overview' },
  { label: '跟随无人艇', value: 'follow-usv' },
  { label: '跟随无人机', value: 'follow-uav' },
  { label: '灯塔视角', value: 'lighthouse' },
]

const commandButtons = [
  { label: '起飞', value: 'takeoff' },
  { label: '降落', value: 'land' },
  { label: '开始任务', value: 'startMission' },
  { label: '停止任务', value: 'stopMission' },
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
  const devices = displayedNodes.value.filter((node) => ['UAV', 'USV', 'LIGHTHOUSE'].includes(node.type))
  if (devices.length > 0) return devices
  return [
    {
      id: -1,
      code: 'USV-01',
      name: '协同无人艇',
      type: 'USV',
      status: 'UNKNOWN',
      host: null,
      port: null,
      endpoint: '',
      rosNamespace: null,
      lastHeartbeatAt: null,
      heartbeatAgeSeconds: -1,
      source: 'LOCAL',
      instanceId: null,
      positionX: null,
      positionY: null,
      positionZ: null,
      detail: '等待运行监控数据',
    } as RuntimeNode,
    {
      id: -2,
      code: 'UAV-01',
      name: '协同无人机',
      type: 'UAV',
      status: 'UNKNOWN',
      host: null,
      port: null,
      endpoint: '',
      rosNamespace: null,
      lastHeartbeatAt: null,
      heartbeatAgeSeconds: -1,
      source: 'LOCAL',
      instanceId: null,
      positionX: null,
      positionY: null,
      positionZ: null,
      detail: '等待运行监控数据',
    } as RuntimeNode,
  ]
})

const selectedNode = computed(() => runtimeNodeByCode.value.get(normalizeDeviceCode(selectedDeviceCode.value)) ?? null)
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
    value: `${realtimePoseCount.value}/2`,
    tone: realtimePoseCount.value >= 2 ? 'online' : 'warning',
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
    await issueRuntimeCommand({
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

async function toggleTrajectory() {
  trajectoryVisible.value = !trajectoryVisible.value
  unityPanel.value?.toggleTrajectory(trajectoryVisible.value)
  lastUnityEvent.value = `toggleTrajectory:${trajectoryVisible.value ? 'show' : 'hide'}`
  void recordRuntimeCommand('TOGGLE_TRAJECTORY', 'Unity 切换轨迹显示状态', selectedDeviceCode.value, {
    visible: trajectoryVisible.value,
  }).catch(() => undefined)
}

async function sendCommand(command: string) {
  const commandMap: Record<string, RuntimeCommandType> = {
    takeoff: 'TAKEOFF',
    land: 'LAND',
    startMission: 'START_MISSION',
    stopMission: 'STOP_MISSION',
  }
  const commandType = commandMap[command]
  if (!commandType) {
    ElMessage.error(`未知控制指令：${command}`)
    return
  }
  unityPanel.value?.sendControlCommand(command, selectedDeviceCode.value)
  lastUnityEvent.value = `command:${command}`
  ElMessage.success(`已发送到 Unity：${commandType}`)
  void recordRuntimeCommand(commandType, '系统总览快捷控制指令', selectedDeviceCode.value, { command }).catch(() => undefined)
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

  if (typeof payload.deviceCode === 'string' && payload.deviceCode.trim()) selectedDeviceCode.value = payload.deviceCode
  if (typeof payload.mode === 'string') selectedCameraMode.value = payload.mode
  if (typeof payload.visible === 'boolean') trajectoryVisible.value = payload.visible
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
      <header class="overview-header">
        <div>
          <p class="overview-kicker">UAV-USV RUNTIME CONSOLE</p>
          <h2>系统总览</h2>
          <span>聚焦 ROS/Gazebo、Unity WebGL、实时位姿和快捷控制。</span>
        </div>
        <div class="overview-runtime-summary">
          <strong>{{ onlineNodeCount }} / {{ displayedNodes.length }}</strong>
          <span>实时节点在线</span>
        </div>
      </header>

      <div class="overview-status-strip">
        <article v-for="card in topStatusCards" :key="card.label" class="overview-status-card" :class="card.tone">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.detail }}</small>
        </article>
      </div>

      <div class="overview-main-grid">
        <section class="overview-stage-panel">
          <div class="overview-stage-header">
            <div>
              <h3>Unity 三维态势</h3>
              <span>当前任务：{{ taskStateText }}</span>
            </div>
            <div class="overview-stage-signals">
              <b :class="{ online: rosBridgeOnline }">ROS2 WebSocket</b>
              <b :class="{ online: unityReady }">Unity WebGL</b>
            </div>
          </div>

          <div class="overview-toolbar">
            <div class="overview-selected-device">
              <span>当前对象</span>
              <strong>{{ selectedDeviceCode }}</strong>
              <small>{{ selectedNode?.detail ?? '等待实时状态' }}</small>
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
            <button class="overview-tool-button" type="button" @click="focusSelectedDevice">聚焦设备</button>
            <button class="overview-tool-button" type="button" @click="toggleTrajectory">
              {{ trajectoryVisible ? '隐藏轨迹' : '显示轨迹' }}
            </button>
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

        <aside class="overview-ops-panel">
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

          <section>
            <h3>设备选择</h3>
            <div class="overview-device-list">
              <button
                v-for="device in selectableDevices"
                :key="device.code"
                type="button"
                :class="{ active: normalizeDeviceCode(device.code) === normalizeDeviceCode(selectedDeviceCode) }"
                @click="selectDevice(device.code)"
              >
                <b>{{ device.code }}</b>
                <span>{{ device.status }}</span>
              </button>
            </div>
          </section>

          <section>
            <h3>快捷指令</h3>
            <div class="overview-command-grid">
              <button v-for="command in commandButtons" :key="command.value" type="button" @click="sendCommand(command.value)">
                {{ command.label }}
              </button>
            </div>
          </section>
        </aside>
      </div>

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
    </section>
  </ConsoleLayout>
</template>
