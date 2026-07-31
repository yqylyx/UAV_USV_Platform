<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft,
  Box,
  Camera,
  Grid2X2,
  Layers3,
  Pause,
  Play,
  Square,
  XOctagon,
} from '@lucide/vue'

import type { RuntimeCommandStatus } from '@/api/runtimeControl'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import UnifiedVehicleControl from '@/components/control/UnifiedVehicleControl.vue'
import type { MissionTrajectorySessionState } from '@/stores/missionTrajectorySession'
import type { UnityTrajectoryFrame } from '@/stores/trajectory'
import type { AlgorithmRuntimeFrame, MissionDetail } from '@/types/mission'
import type { RuntimeNode } from '@/types/monitoring'

import AlgorithmTrajectoryMap from './AlgorithmTrajectoryMap.vue'
import MissionTrajectoryMap from './MissionTrajectoryMap.vue'

type ExecutionViewMode = '2d' | '3d' | 'vision'
type VisualDisplayMode = 'grid' | 'focus'

const props = defineProps<{
  detail: MissionDetail
  nodes: RuntimeNode[]
  trajectoryFrame: UnityTrajectoryFrame | null
  algorithmFrame: AlgorithmRuntimeFrame | null
  sessionState: MissionTrajectorySessionState
  sessionRevision: number
  selectedDeviceCode: string
  feedback: Record<string, RuntimeCommandStatus | undefined>
  operationalStates: Record<string, string | undefined>
  mode: ExecutionViewMode
  visualDisplayMode: VisualDisplayMode
  visualConnected: boolean
  unityRunSynchronized: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [code: string]
  vehicleCommand: [command: VehicleQuickCommand]
  missionAction: [action: 'pause' | 'resume' | 'complete' | 'cancel']
  events: []
  modeChange: [mode: ExecutionViewMode]
  visualGrid: []
  placeThreat: [x: number, y: number]
}>()

const layers = ref(['轨迹', '航路点', '包围圈'])
const recentEvents = computed(() => props.detail.events.slice(0, 5))
const externalAlgorithm = computed(() =>
  ['GB_SFLA_CS', 'ESCORT_GUARD'].includes(props.detail.mission.algorithmCode),
)
const visualStatusText = computed(() => {
  if (!props.visualConnected) return '任务视觉连接中'
  if (props.visualDisplayMode === 'grid') return '六路任务视觉'
  return `${props.selectedDeviceCode.toUpperCase()} 实时视觉`
})

const runSyncText = computed(() => {
  if (props.mode === 'vision') return visualStatusText.value
  if (props.mode === '3d' && !props.unityRunSynchronized) return '3D 正在同步当前 RUN'
  const runNo = props.detail.currentRun?.runNo ?? '--'
  const sequence = props.algorithmFrame?.sequence ?? 0
  return `RUN ${runNo} · 同步帧 ${sequence}`
})

function close() {
  emit('modeChange', '2d')
  emit('close')
}

function placeThreat(x: number, y: number) {
  emit('placeThreat', x, y)
}
</script>

<template>
  <section class="mission-execution-overlay">
    <header class="execution-header">
      <button :disabled="busy" @click="close">
        <ArrowLeft :size="18" />返回任务中心
      </button>
      <div>
        <small>{{ detail.mission.code }} · RUN {{ detail.currentRun?.runNo || '--' }}</small>
        <h2>{{ detail.mission.name }}</h2>
      </div>
      <div class="execution-stats">
        <span>{{ detail.mission.status }}</span>
        <span>{{ detail.mission.stage }}</span>
        <span>
          在线
          {{ nodes.filter(node => node.status === 'ONLINE' && ['UAV', 'USV'].includes(node.type)).length }}
          /
          {{ detail.devices.filter(device => ['UAV', 'USV'].includes(device.type || '')).length }}
        </span>
      </div>
      <div class="execution-actions">
        <button
          v-if="detail.mission.status === 'RUNNING'"
          :disabled="busy"
          @click="emit('missionAction', 'pause')"
        >
          <Pause :size="17" />暂停任务
        </button>
        <button
          v-if="detail.mission.status === 'PAUSED'"
          :disabled="busy"
          @click="emit('missionAction', 'resume')"
        >
          <Play :size="17" />继续任务
        </button>
        <button
          :disabled="busy || !['RUNNING', 'PAUSED'].includes(detail.mission.status)"
          @click="emit('missionAction', 'complete')"
        >
          <Square :size="17" />完成任务
        </button>
        <button
          class="danger"
          :disabled="busy || !['RUNNING', 'PAUSED', 'READY'].includes(detail.mission.status)"
          @click="emit('missionAction', 'cancel')"
        >
          <XOctagon :size="17" />终止任务
        </button>
      </div>
    </header>

    <div class="execution-body">
      <aside class="execution-tree">
        <h3>作战对象</h3>
        <section v-for="type in ['UAV', 'USV']" :key="type">
          <b>{{ type }}</b>
          <button
            v-for="node in nodes.filter(item => item.type === type)"
            :key="node.code"
            :class="{ selected: node.code.toLowerCase() === selectedDeviceCode.toLowerCase() }"
            @click="emit('select', node.code)"
          >
            <span>
              <Camera v-if="mode === 'vision'" :size="13" />
              {{ node.code.toUpperCase() }}
            </span>
            <i :class="{ online: node.status === 'ONLINE' }" />
          </button>
        </section>

        <section v-if="mode === 'vision'" class="visual-channel-controls">
          <b>视觉通道</b>
          <button
            :class="{ selected: visualDisplayMode === 'grid' }"
            @click="emit('visualGrid')"
          >
            <span><Grid2X2 :size="13" />六路总览</span>
          </button>
          <small>点击上方任意设备可聚焦对应相机</small>
        </section>
        <section v-else>
          <b>图层</b>
          <el-checkbox-group v-model="layers">
            <el-checkbox
              v-for="layer in ['轨迹', '航路点', '包围圈']"
              :key="layer"
              :value="layer"
            >
              {{ layer }}
            </el-checkbox>
          </el-checkbox-group>
        </section>
      </aside>

      <main class="execution-stage">
        <div class="mode-switch">
          <button :class="{ active: mode === '2d' }" @click="emit('modeChange', '2d')">
            <Layers3 :size="16" />2D 轨迹
          </button>
          <button :class="{ active: mode === '3d' }" @click="emit('modeChange', '3d')">
            <Box :size="16" />3D Unity
          </button>
          <button :class="{ active: mode === 'vision' }" @click="emit('modeChange', 'vision')">
            <Camera :size="16" />设备视觉
          </button>
        </div>
        <span class="shared-run-indicator">
          {{ runSyncText }}
        </span>

        <AlgorithmTrajectoryMap
          v-if="mode === '2d' && externalAlgorithm"
          :frame="algorithmFrame"
          :mission-name="detail.mission.name"
          :selected-device-code="selectedDeviceCode"
          @select="emit('select', $event)"
          @place-threat="placeThreat"
        />
        <MissionTrajectoryMap
          v-else-if="mode === '2d'"
          :mission-name="detail.mission.name"
          :mission-status="detail.mission.status"
          :selected-device-code="selectedDeviceCode"
          :trajectory-frame="trajectoryFrame"
          :session-state="sessionState"
          :session-revision="sessionRevision"
          @select-device="emit('select', $event)"
        />
        <div
          v-else
          class="execution-unity-viewport"
          :class="{ vision: mode === 'vision' }"
          data-unity-runtime-viewport="mission-execution"
        />
      </main>

      <aside class="execution-control">
        <UnifiedVehicleControl
          :devices="nodes"
          :selected-device-code="selectedDeviceCode"
          :feedback="feedback"
          :operational-states="operationalStates"
          :busy="busy"
          @select="emit('select', $event)"
          @command="emit('vehicleCommand', $event)"
        />
        <button class="all-events" @click="emit('events')">查看全部事件</button>
      </aside>
    </div>

    <footer class="execution-footer">
      <article v-for="event in recentEvents" :key="event.id">
        <time>{{ new Date(event.occurredAt).toLocaleTimeString() }}</time>
        <b>{{ event.title }}</b>
        <span>{{ event.message }}</span>
      </article>
    </footer>
  </section>
</template>

<style scoped>
.mission-execution-overlay {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  grid-template-rows: auto 1fr auto;
  color: #dff5f3;
  background: #020e15;
}

.execution-header {
  display: flex;
  align-items: center;
  gap: 18px;
  min-height: 72px;
  padding: 10px 18px;
  border-bottom: 1px solid #17414b;
  background: linear-gradient(90deg, #041923, #03131c);
}

.execution-header button,
.mode-switch button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 11px;
  color: #cde2e2;
  border: 1px solid #2a515b;
  border-radius: 5px;
  background: #08232d;
  cursor: pointer;
}

.execution-header button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.execution-header h2 {
  margin: 3px 0;
  font-size: 18px;
}

.execution-header small {
  color: #53d4e2;
}

.execution-stats {
  display: flex;
  gap: 7px;
  margin-left: auto;
  color: #8fb0b4;
}

.execution-stats span {
  padding: 5px 8px;
  border: 1px solid rgba(70, 156, 173, .14);
  border-radius: 4px;
  background: rgba(62, 151, 168, .06);
  font-size: 10px;
}

.execution-actions {
  display: flex;
  gap: 7px;
}

.execution-actions .danger {
  color: #ff7474;
  border-color: #8c3940;
}

.execution-body {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr) 350px;
  gap: 10px;
  min-height: 0;
  padding: 10px;
}

.execution-tree,
.execution-control {
  padding: 12px;
  overflow: auto;
  border: 1px solid #173d47;
  background: #041822;
}

.execution-tree section {
  display: grid;
  gap: 6px;
  margin: 14px 0;
}

.execution-tree section > b {
  color: #6ce4d5;
}

.execution-tree button {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  color: #b8d0d1;
  border: 1px solid transparent;
  background: #09212b;
  cursor: pointer;
}

.execution-tree button > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.execution-tree button.selected {
  color: #6ce4d5;
  border-color: rgba(108, 228, 213, .45);
  background: rgba(108, 228, 213, .08);
}

.execution-tree i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #64777a;
}

.execution-tree i.online {
  background: #55e7a7;
}

.execution-tree :deep(.el-checkbox-group) {
  display: grid;
}

.visual-channel-controls small {
  color: #698d91;
  font-size: 10px;
  line-height: 1.5;
}

.execution-stage {
  position: relative;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #17414b;
  background: #03141c;
}

.execution-stage :deep(.mission-trajectory-map) {
  width: 100%;
  height: 100%;
}

.mode-switch {
  position: absolute;
  z-index: 3;
  top: 10px;
  left: 50%;
  display: flex;
  transform: translateX(-50%);
}

.mode-switch .active {
  color: #6ce4d5;
  border-color: #6ce4d5;
  background: #0b3540;
}

.shared-run-indicator {
  position: absolute;
  z-index: 3;
  top: 14px;
  right: 12px;
  color: #59dcad;
  font-size: 9px;
}

.shared-run-indicator::before {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-radius: 50%;
  background: #55e7a7;
  box-shadow: 0 0 7px #55e7a7;
  content: "";
}

.execution-unity-viewport {
  position: absolute;
  inset: 52px 0 0;
}

.execution-unity-viewport.vision {
  background: #02090d;
}

.all-events {
  width: 100%;
  height: 36px;
  margin-top: 10px;
  color: #d7eeee;
  border: 1px solid #2b5660;
  background: #08232d;
}

.execution-footer {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  padding: 9px 12px;
  border-top: 1px solid #173d47;
}

.execution-footer article {
  min-width: 0;
  padding: 8px;
  background: #061b24;
}

.execution-footer time,
.execution-footer b,
.execution-footer span {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.execution-footer time {
  color: #5f8b91;
  font-size: 10px;
}

.execution-footer span {
  color: #89a8ac;
  font-size: 11px;
}

@media (max-width: 1200px) {
  .execution-body {
    grid-template-columns: 160px minmax(0, 1fr) 300px;
  }

  .execution-header {
    flex-wrap: wrap;
  }

  .execution-stats {
    margin-left: 0;
  }
}
</style>
