<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  Camera,
  CheckCircle2,
  CircleStop,
  Pause,
  Play,
  RefreshCw,
  Send,
  SquareStack,
} from '@lucide/vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

const unityPanel = ref<InstanceType<typeof UnityWebglPanel> | null>(null)
const unityReady = ref(false)
const lastMessage = ref<UnityMessage | null>(null)
const selectedDevice = ref('')
const logs = ref<string[]>([])
const sceneLocked = computed(() => state.mission === 'RUNNING' || state.mission === 'PAUSED')

const state = reactive({
  algorithm: 'GB_SFLA_CS',
  seed: 20260814,
  uavCount: 3,
  usvCount: 3,
  uavSpeed: 5,
  usvSpeed: 1,
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
  && state.usvSpeed <= 2)

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
    protocolVersion: '3.0',
    buildId: 'vue-virtual-fleet-v3',
  })
}

function onUnityError(message: string) {
  unityReady.value = false
  addLog(`Unity 错误: ${message}`)
}

function onUnityMessage(message: UnityMessage) {
  if (message.type !== 'vueCommandReceived') {
    lastMessage.value = message
  }
  if (message.type === 'platformBridgeReady') unityReady.value = message.payload?.ready === true
  if (message.type === 'scenarioReady') addLog(`scenarioReady: ${message.payload?.success === true ? 'success' : 'failed'}`)
  if (message.type === 'poseFrameApplied') addLog(`poseFrameApplied: sequence=${message.payload?.sequence ?? '-'}`)
  if (message.type === 'cameraChanged') addLog(`cameraChanged: ${message.payload?.deviceCode ?? '-'}`)
}

function validateSpeed(value: number, max: number) {
  return Math.max(0, Math.min(max, Number.isFinite(value) ? value : 0))
}

function generateScenario() {
  if (sceneLocked.value) return
  state.uavSpeed = validateSpeed(state.uavSpeed, 15)
  state.usvSpeed = validateSpeed(state.usvSpeed, 2)
  // Each generated scenario needs an isolated run id so delayed pose
  // messages from an older WebGL instance cannot rewind its sequence.
  state.runId = Date.now()
  state.sequence = 0
  state.mission = 'STOPPED'
  send('loadScenario', {
    runtimeMode: 'VIRTUAL_SIMULATION',
    algorithmCode: state.algorithm,
    runId: state.runId,
    uavCount: state.uavCount,
    usvCount: state.usvCount,
    targetCount: 1,
    initialSpeedMps: state.algorithm === 'GB_SFLA_CS' ? state.uavSpeed : state.usvSpeed,
    seed: state.seed,
  })
}

function startMission() {
  if (!unityReady.value || !speedValid.value) return
  state.mission = 'RUNNING'
  send('missionStart', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
  sendPoseBatch()
}

function pauseMission() {
  if (state.mission !== 'RUNNING') return
  state.mission = 'PAUSED'
  send('missionPause', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
}

function stopMission() {
  state.mission = 'STOPPED'
  send('missionStop', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
}

function resetMission() {
  state.mission = 'STOPPED'
  state.sequence = 0
  send('missionReset', { runtimeMode: 'VIRTUAL_SIMULATION', runId: state.runId })
}

function sendPoseBatch() {
  if (!unityReady.value || state.mission !== 'RUNNING') return
  state.sequence += 1
  const vehicles = vehicleCodes.value.map((deviceCode, index) => {
    const isUav = deviceCode.startsWith('UAV-')
    const speedMps = isUav ? state.uavSpeed : state.usvSpeed
    return {
      deviceCode,
      deviceType: isUav ? 'UAV' : 'USV',
      eastM: Math.sin(index + state.sequence * 0.05) * 20,
      northM: Math.cos(index + state.sequence * 0.05) * 20,
      upM: isUav ? 25 + (index % 4) * 4 : 0,
      velocityEastMps: speedMps,
      velocityNorthMps: 0,
      velocityUpMps: 0,
      headingDeg: 90,
      speedMps,
      role: state.algorithm === 'GB_SFLA_CS' ? 'capture' : 'escort',
      targetCode: 'TARGET-001',
      state: isUav ? 'AIRBORNE' : 'SAILING',
      valid: true,
    }
  })
  addLog(`applyPoseBatch: sequence=${state.sequence}`)
  send('applyPoseBatch', {
    runtimeMode: 'VIRTUAL_SIMULATION',
    runId: state.runId,
    sequence: state.sequence,
    sampleTime: Date.now(),
    vehicles,
    targets: [{
      deviceCode: 'TARGET-001',
      eastM: 0,
      northM: 0,
      upM: 0,
      headingDeg: 0,
      speedMps: 0,
      state: 'ACTIVE',
      valid: true,
    }],
  })
}

function selectDevice(code: string) {
  selectedDevice.value = code
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

let poseTimer: number | null = null
onMounted(() => {
  poseTimer = window.setInterval(sendPoseBatch, 1000)
})

onBeforeUnmount(() => {
  if (poseTimer !== null) window.clearInterval(poseTimer)
})
</script>

<template>
  <ConsoleLayout
    title="虚拟编队任务配置"
    eyebrow="VIRTUAL FLEET / UNITY BRIDGE V3"
    :show-refresh="false"
  >
    <div class="virtual-fleet-page">
      <section class="vf-hero">
        <div>
          <p class="eyebrow">INDEPENDENT UNITY INTEGRATION</p>
          <h2>虚拟编队算法验证</h2>
          <p>独立 Unity WebGL 实例，直接测试场景配置、批量位姿、任务状态和相机回执。</p>
        </div>
        <div class="vf-hero-status" :class="{ ready: unityReady }">
          <CheckCircle2 :size="18" />
          {{ unityReady ? 'UNITY BRIDGE ONLINE' : 'WAITING FOR UNITY' }}
        </div>
      </section>

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
            <div class="vf-two-col">
              <label>UAV 数量
                <input v-model.number="state.uavCount" type="number" min="1" max="100" :disabled="sceneLocked">
              </label>
              <label>USV 数量
                <input v-model.number="state.usvCount" type="number" min="1" max="100" :disabled="sceneLocked">
              </label>
              <label>UAV 初始速度 m/s
                <input v-model.number="state.uavSpeed" type="number" min="0" max="15" step="0.1" :disabled="sceneLocked">
                <small>上限 15 m/s</small>
              </label>
              <label>USV 初始速度 m/s
                <input v-model.number="state.usvSpeed" type="number" min="0" max="2" step="0.1" :disabled="sceneLocked">
                <small>上限 2 m/s</small>
              </label>
            </div>
            <label>随机种子
              <input v-model.number="state.seed" type="number" step="1" :disabled="sceneLocked">
            </label>
            <div class="vf-actions">
              <button class="vf-button primary" type="button" :disabled="sceneLocked || !unityReady" @click="generateScenario">
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
              <button class="vf-button success" type="button" :disabled="state.mission === 'RUNNING' || !unityReady || !speedValid" @click="startMission">
                <Play :size="15" /> 开始
              </button>
              <button class="vf-button" type="button" :disabled="state.mission !== 'RUNNING'" @click="pauseMission">
                <Pause :size="15" /> 暂停
              </button>
              <button class="vf-button danger" type="button" :disabled="state.mission === 'STOPPED'" @click="stopMission">
                <CircleStop :size="15" /> 停止
              </button>
            </div>
            <p v-if="!speedValid" class="vf-error">速度超过协议上限，请修正后再开始任务。</p>
          </section>

          <section class="vf-panel">
            <div class="vf-panel-head"><h3>回执日志</h3><span>{{ logs.length }} EVENTS</span></div>
            <div class="vf-log">
              <div v-for="entry in logs" :key="entry">{{ entry }}</div>
              <span v-if="!logs.length">等待 Unity 回执...</span>
            </div>
          </section>
        </aside>

        <section class="vf-stage-panel">
          <div class="vf-stage-head">
            <div><h3>Unity WebGL 虚拟场景</h3><span>独立运行实例：virtual-fleet-v3-01</span></div>
            <strong>{{ state.uavCount }} UAV / {{ state.usvCount }} USV</strong>
          </div>
          <div class="vf-unity-stage">
            <UnityWebglPanel
              ref="unityPanel"
              runtime-scope="VIRTUAL_FLEET"
              runtime-instance-id="virtual-fleet-v3-01"
              @unity-ready="onUnityReady"
              @unity-error="onUnityError"
              @unity-message="onUnityMessage"
            />
          </div>
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
            <button class="vf-follow" type="button" :disabled="!unityReady" @click="setOverviewCamera">
              <Camera :size="15" /> 全局视角
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
          <section class="vf-panel">
            <div class="vf-panel-head"><h3>最近回执</h3><span>{{ lastMessage?.type || 'NONE' }}</span></div>
            <pre>{{ JSON.stringify(lastMessage || {}, null, 2) }}</pre>
          </section>
          <section class="vf-panel">
            <div class="vf-panel-head"><h3>物理速度规则</h3><span>m/s</span></div>
            <div class="vf-speed-rule"><strong>UAV</strong><span>{{ state.uavSpeed.toFixed(1) }} / 15</span></div>
            <div class="vf-speed-bar"><i :style="{ width: `${Math.min(100, state.uavSpeed / 15 * 100)}%` }"></i></div>
            <div class="vf-speed-rule"><strong>USV</strong><span>{{ state.usvSpeed.toFixed(1) }} / 2</span></div>
            <div class="vf-speed-bar usv"><i :style="{ width: `${Math.min(100, state.usvSpeed / 2 * 100)}%` }"></i></div>
            <p class="vf-note">Unity 内部按 PresentationCoordinateScale = 0.18 转换。</p>
          </section>
        </aside>
      </div>
    </div>
  </ConsoleLayout>
</template>

<style scoped>
.virtual-fleet-page { display: grid; gap: 14px; }
.vf-hero {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 18px 20px; color: #eafffb; background: linear-gradient(135deg, #092a31, #07181e);
  border: 1px solid rgba(108, 228, 213, .24); border-radius: 8px;
}
.vf-hero h2 { margin: 3px 0 6px; color: #f4fffd; font-size: 28px; }
.vf-hero p:not(.eyebrow) { color: #8fb4b2; font-size: 13px; }
.vf-hero-status { display: flex; align-items: center; gap: 8px; color: #ffcf72; font-size: 11px; font-weight: 900; }
.vf-hero-status.ready { color: #68e6a8; }
.vf-grid { display: grid; grid-template-columns: 290px minmax(0, 1fr) 290px; gap: 14px; align-items: start; }
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
.vf-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 13px; }
.vf-button, .vf-follow, .vf-device { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 0 10px; color: #dff8f4; background: rgba(108, 228, 213, .06); border: 1px solid rgba(108, 228, 213, .24); border-radius: 4px; cursor: pointer; }
.vf-button:hover:not(:disabled), .vf-follow:hover:not(:disabled), .vf-device:hover { border-color: #6ce4d5; color: #6ce4d5; }
.vf-button.primary { color: #061113; background: #6ce4d5; border-color: #6ce4d5; font-weight: 800; }
.vf-button.success { color: #68e6a8; border-color: rgba(104, 230, 168, .45); }
.vf-button.danger { color: #ff8179; border-color: rgba(255, 129, 121, .44); }
.vf-button:disabled, .vf-follow:disabled { cursor: not-allowed; opacity: .4; }
.vf-error { margin-top: 10px; color: #ff8179; font-size: 11px; }
.vf-stage-panel { padding: 0; overflow: hidden; }
.vf-stage-head { padding: 14px 15px; border-bottom: 1px solid rgba(108, 228, 213, .15); }
.vf-stage-head strong { color: #ffcf72; font-size: 12px; }
.vf-unity-stage { min-height: 540px; background: #031015; }
.vf-unity-stage :deep(.unity-webgl-panel) { width: 100%; height: 540px; }
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
.vf-log { max-height: 160px; overflow: auto; color: #8fb4b2; font: 10px/1.7 Consolas, monospace; }
.vf-speed-rule { display: flex; justify-content: space-between; gap: 8px; margin-top: 11px; color: #dff8f4; font-size: 11px; }
.vf-speed-rule span { color: #8fb4b2; }
.vf-speed-bar { height: 5px; margin-top: 5px; overflow: hidden; background: #18343a; border-radius: 3px; }
.vf-speed-bar i { display: block; height: 100%; background: #f5ce6b; }
.vf-speed-bar.usv i { background: #63d9e7; }
@media (max-width: 1240px) { .vf-grid { grid-template-columns: 280px minmax(0, 1fr); } .vf-grid > .vf-column:last-child { grid-column: 1 / -1; grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 800px) { .vf-hero { align-items: flex-start; flex-direction: column; } .vf-grid, .vf-grid > .vf-column:last-child { grid-template-columns: 1fr; } .vf-grid > .vf-column:last-child { grid-column: auto; } .vf-unity-stage, .vf-unity-stage :deep(.unity-webgl-panel) { min-height: 360px; height: 360px; } .vf-two-col { grid-template-columns: 1fr; } }
</style>
