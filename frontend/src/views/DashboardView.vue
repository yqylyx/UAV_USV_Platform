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

const assets = [
  { code: 'UAV-01', role: '高空侦察', detail: '目标视觉锁定 / 东北航线', type: 'air', status: 'READY' },
  { code: 'UAV-02', role: '侧翼压制', detail: '轨迹预测 / 西北航线', type: 'air', status: 'READY' },
  { code: 'UAV-03', role: '低空补盲', detail: '海面遮挡补偿 / 南向跟随', type: 'air', status: 'READY' },
  { code: 'USV-01', role: '正面拦截', detail: '主追踪艇 / 收敛航向', type: 'sea', status: 'READY' },
  { code: 'USV-02', role: '左翼封锁', detail: '速度匹配 / 半径约束', type: 'sea', status: 'READY' },
  { code: 'USV-03', role: '右翼封锁', detail: '水面包络 / 目标截断', type: 'sea', status: 'READY' },
]

const phases = [
  { step: '1', title: '目标发现', text: 'UAV 先行侦察，USV 接收目标航迹与速度估计。' },
  { step: '2', title: '协同分配', text: '算法服务按距离、角度和任务角色分配包围位置。' },
  { step: '3', title: '闭环围捕', text: 'Unity 显示态势，ROS2 持续反馈位姿，Web 统一控制任务。' },
]

const readouts = [
  { label: '围捕完成度', value: '72%', text: '包络半径持续收缩' },
  { label: '目标相对速度', value: '2.8 m/s', text: '预测航向稳定' },
  { label: '通信延迟', value: '38 ms', text: 'ROS2 / Unity 链路正常' },
  { label: '安全距离', value: '15.4 m', text: '未触发碰撞预警' },
]

const links = [
  { name: 'ROS2 / Gazebo', value: 88 },
  { name: 'WebSocket Bridge', value: 92 },
  { name: 'Unity WebGL View', value: 84 },
  { name: 'Mission Control', value: 76 },
]

const architecture = [
  { layer: '5', title: '展示交互层', text: 'Vue 控制台 / Unity 三维态势', state: '建设中' },
  { layer: '4', title: '业务服务层', text: '设备、任务、状态、日志、评估', state: '建设中' },
  { layer: '3', title: '智能算法层', text: '识别、分配、路径规划、围捕控制', state: '待接入' },
  { layer: '2', title: '通信与认知层', text: 'ROS2 / WebSocket / 多源状态共享', state: '已打通' },
  { layer: '1', title: '仿真与执行层', text: 'Gazebo / UAV / USV / Unity 场景', state: '已打通' },
]

const monitoringStore = useMonitoringStore()
const unityPanel = ref<UnityPanelExpose | null>(null)
const selectedDeviceCode = ref('USV-01')
const selectedCameraMode = ref('overview')
const trajectoryVisible = ref(true)
const unityConnection = ref('等待 WebGL 构建')
const lastUnityEvent = ref('暂无 Unity 回传事件')
let poseFrameSequence = 0
let heartbeatTimer: number | null = null
const unityInstanceId = `vue-webgl:${window.location.host}:${Math.random().toString(36).slice(2, 10)}`

const cameraModes = [
  { label: '总览', value: 'overview' },
  { label: '跟随无人艇', value: 'follow-usv' },
  { label: '跟随无人机', value: 'follow-uav' },
  { label: '灯塔视角', value: 'lighthouse' },
]

function normalizeDeviceCode(code: string) {
  return code.trim().toLowerCase()
}

const runtimeNodeByCode = computed(() => {
  const map = new Map<string, RuntimeNode>()
  monitoringStore.nodes.forEach((node) => map.set(normalizeDeviceCode(node.code), node))
  return map
})
const missionAssets = computed(() =>
  assets.map((asset) => {
    const runtimeNode = runtimeNodeByCode.value.get(normalizeDeviceCode(asset.code))
    const online = runtimeNode?.status === 'ONLINE'
    return {
      ...asset,
      runtimeNode,
      online,
      status: online ? 'ONLINE' : runtimeNode ? runtimeNode.status : 'WAITING',
      detail: runtimeNode?.detail || asset.detail,
    }
  }),
)
const selectedAsset = computed(() =>
  missionAssets.value.find((asset) => normalizeDeviceCode(asset.code) === normalizeDeviceCode(selectedDeviceCode.value)),
)
const cooperativeUnitCount = computed(() => missionAssets.value.length)
const onlineCooperativeUnitCount = computed(() => missionAssets.value.filter((asset) => asset.online).length)
const bridgeHealth = computed(() => links.find((link) => link.name === 'WebSocket Bridge')?.value ?? 0)
const unityReady = computed(() => unityConnection.value.includes('Unity WebGL 已连接'))
const rosBridgeOnline = computed(() =>
  monitoringStore.nodes.some((node) => node.type === 'ROS_NODE' && node.status === 'ONLINE'),
)
const realtimePoseCount = computed(
  () =>
    monitoringStore.nodes.filter(
      (node) => ['UAV', 'USV'].includes(node.type) && node.status === 'ONLINE' && hasRuntimePosition(node),
    ).length,
)
const overviewLinkState = computed(() => {
  if (!unityReady.value) return '等待 WebGL 接入'
  if (rosBridgeOnline.value && realtimePoseCount.value > 0) return '实时位姿同步中'
  if (rosBridgeOnline.value) return 'ROS 已连接，等待载体位姿'
  return 'Unity 已接入，等待 ROS 实时数据'
})
const overviewLinkDetail = computed(() => {
  if (!unityReady.value) return 'Unity WebGL 构建包尚未完成加载'
  if (rosBridgeOnline.value && realtimePoseCount.value > 0) return `已接收 ${realtimePoseCount.value} 个协同载体实时位姿`
  if (rosBridgeOnline.value) return 'ROS WebSocket 已连接，尚未收到 UAV / USV 有效位姿'
  return '三维场景已加载，ROS/Gazebo 实时桥接暂未在线'
})
function hasRuntimePosition(node: RuntimeNode) {
  return node.positionX !== null && node.positionY !== null && node.positionZ !== null
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
  await recordRuntimeCommand('SELECT_DEVICE', '系统总览选择协同设备', deviceCode)
  unityPanel.value?.selectDevice(deviceCode)
}

async function focusSelectedDevice() {
  await recordRuntimeCommand('FOCUS_DEVICE', 'Unity 视角聚焦当前设备')
  unityPanel.value?.focusDevice(selectedDeviceCode.value)
}

async function switchCamera(mode: string) {
  selectedCameraMode.value = mode
  await recordRuntimeCommand('SWITCH_CAMERA', 'Unity 切换态势观察视角', selectedDeviceCode.value, { mode })
  unityPanel.value?.switchCamera(mode)
}

async function toggleTrajectory() {
  trajectoryVisible.value = !trajectoryVisible.value
  await recordRuntimeCommand('TOGGLE_TRAJECTORY', 'Unity 切换轨迹显示状态', selectedDeviceCode.value, {
    visible: trajectoryVisible.value,
  })
  unityPanel.value?.toggleTrajectory(trajectoryVisible.value)
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
  await recordRuntimeCommand(commandType, '系统总览快捷控制指令', selectedDeviceCode.value, { command })
  unityPanel.value?.sendControlCommand(command, selectedDeviceCode.value)
  ElMessage.success(`指令已下发：${commandType}`)
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
    <section class="mission-overview" aria-label="海空协同围捕态势总览">
      <header class="mission-hero">
        <div>
          <p class="mission-kicker">UAV-USV COOPERATIVE ENCIRCLEMENT COMMAND</p>
          <h2>海空协同围捕态势总览</h2>
          <p>
            面向无人机、无人艇协同任务，融合 ROS2/Gazebo 仿真、Unity3D 三维态势与 Web 任务控制，
            形成感知、通信、决策、协同与展示的一体化控制闭环。
          </p>
        </div>
        <div class="mission-link-summary" aria-label="联调链路状态">
          <div class="mission-link-summary-head">
            <span>联调链路</span>
            <strong>{{ overviewLinkState }}</strong>
            <small>{{ overviewLinkDetail }}</small>
          </div>
          <div class="mission-link-summary-metrics">
            <div>
              <b>{{ cooperativeUnitCount }}</b>
              <span>协同单元</span>
            </div>
            <div>
              <b>{{ bridgeHealth }}%</b>
              <span>桥接健康</span>
            </div>
          </div>
          <div class="mission-link-flow" aria-label="ROS 到 Unity 的数据链路">
            <span>ROS2 / Gazebo</span>
            <i></i>
            <span>WebSocket</span>
            <i></i>
            <span>Unity / Vue</span>
          </div>
        </div>
      </header>

      <div class="mission-dashboard">
        <aside class="mission-panel">
          <div class="mission-panel-title">
            <h3>协同编队</h3>
            <span class="mission-tag">{{ onlineCooperativeUnitCount }} / {{ cooperativeUnitCount }} ONLINE</span>
          </div>
          <div class="mission-asset-grid">
            <button
              v-for="asset in missionAssets"
              :key="asset.code"
              class="mission-asset-row"
              :class="{ selected: asset.code === selectedDeviceCode, offline: !asset.online }"
              type="button"
              @click="selectDevice(asset.code)"
            >
              <div class="mission-asset-icon" :class="asset.type">
                {{ asset.type === 'air' ? 'UAV' : 'USV' }}
              </div>
              <div>
                <strong>{{ asset.code }} {{ asset.role }}</strong>
                <span>{{ asset.detail }}</span>
              </div>
              <small>{{ asset.status }}</small>
            </button>
          </div>

          <div class="mission-phase-list">
            <div v-for="phase in phases" :key="phase.step" class="mission-phase">
              <div class="mission-phase-index">{{ phase.step }}</div>
              <div>
                <strong>{{ phase.title }}</strong>
                <span>{{ phase.text }}</span>
              </div>
            </div>
          </div>
        </aside>

        <section class="mission-panel mission-tactical">
          <div class="mission-map-header">
            <div>
              <h3>数字海域三维态势</h3>
              <p>Unity WebGL 场景嵌入系统总览，替代原雷达扫描示意图。</p>
            </div>
            <div class="mission-signal"><i></i> ROS2 WebSocket</div>
            <div class="mission-signal"><i></i> Unity WebGL</div>
          </div>

          <div class="mission-unity-controls">
            <div class="mission-selected-device">
              <span>当前对象</span>
              <strong>{{ selectedDeviceCode }}</strong>
              <small>{{ selectedAsset?.role ?? '未选择设备' }}</small>
            </div>
            <div class="mission-camera-tabs" aria-label="Unity 视角切换">
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
            <button class="mission-control-button" type="button" @click="focusSelectedDevice">
              聚焦设备
            </button>
            <button class="mission-control-button" type="button" @click="toggleTrajectory">
              {{ trajectoryVisible ? '隐藏轨迹' : '显示轨迹' }}
            </button>
          </div>

          <UnityWebglPanel
            ref="unityPanel"
            class="mission-unity-stage"
            @unity-ready="handleUnityReady"
            @unity-message="handleUnityMessage"
            @unity-error="handleUnityError"
          />

          <div class="mission-readouts">
            <div v-for="readout in readouts" :key="readout.label" class="mission-readout">
              <span>{{ readout.label }}</span>
              <strong>{{ readout.value }}</strong>
              <small>{{ readout.text }}</small>
            </div>
          </div>
        </section>

        <aside class="mission-panel">
          <div class="mission-panel-title">
            <h3>任务闭环</h3>
            <span class="mission-tag warn">DEMO MODE</span>
          </div>
          <div class="mission-status-stack">
            <div class="mission-status-card">
              <span>当前阶段</span>
              <strong>协同收敛</strong>
              <small>无人机提供目标航迹，无人艇按包围点位推进。</small>
            </div>
            <div class="mission-status-card">
              <span>指挥链路</span>
              <strong>Web -> Spring Boot -> ROS2</strong>
              <small>管理平台负责任务配置、节点状态和控制命令编排。</small>
            </div>
            <div class="mission-status-card">
              <span>三维态势</span>
              <strong>Unity WebGL 半实物可视化</strong>
              <small>同步 Gazebo 位姿，展示海面、无人艇、无人机和目标。</small>
            </div>
            <div class="mission-status-card">
              <span>Unity 通信</span>
              <strong>{{ unityConnection }}</strong>
              <small>最近事件：{{ lastUnityEvent }}</small>
            </div>
          </div>

          <div class="mission-panel-title compact">
            <h3>快速指令</h3>
            <span class="mission-tag">VUE -> UNITY</span>
          </div>
          <div class="mission-command-grid">
            <button type="button" @click="sendCommand('takeoff')">起飞</button>
            <button type="button" @click="sendCommand('land')">降落</button>
            <button type="button" @click="sendCommand('startMission')">开始任务</button>
            <button type="button" @click="sendCommand('stopMission')">停止任务</button>
          </div>

          <div class="mission-panel-title compact">
            <h3>链路健康</h3>
            <span class="mission-tag">LOW LATENCY</span>
          </div>
          <div class="mission-link-stack">
            <div v-for="link in links" :key="link.name" class="mission-link-row">
              <span>{{ link.name }}</span>
              <div class="mission-bar"><i :style="{ width: `${link.value}%` }"></i></div>
            </div>
          </div>

          <div class="mission-architecture">
            <div v-for="item in architecture" :key="item.layer" class="mission-arch-layer">
              <b>{{ item.layer }}</b>
              <div>
                <strong>{{ item.title }}</strong>
                <span>{{ item.text }}</span>
              </div>
              <em>{{ item.state }}</em>
            </div>
          </div>

          <div class="mission-note">
            本页作为任务态势入口，后续会继续接入运行监控、任务管理、算法服务与 Unity 场景状态。
          </div>
        </aside>
      </div>
    </section>
  </ConsoleLayout>
</template>
