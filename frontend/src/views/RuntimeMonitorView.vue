<script setup lang="ts">
import { Activity, Plane, Play, Radar, RefreshCw, RotateCcw, Search, Ship, Square } from '@lucide/vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { useRuntimeControlStore } from '@/stores/runtimeControl'
import type { DeviceStatus, DeviceType } from '@/types/device'
import type { RuntimeNode } from '@/types/monitoring'
import type { SimulationStatus } from '@/types/runtimeControl'

const monitoringStore = useMonitoringStore()
const controlStore = useRuntimeControlStore()
let controlTimer: number | null = null
let commandTimer: number | null = null
const actionPhase = ref<'idle' | 'starting' | 'stopping'>('idle')
const commandLogDialogVisible = ref(false)
const commandLogPage = ref(1)
const commandLogPageSize = ref(10)

const filters = reactive({
  type: '' as DeviceType | '',
  status: '' as DeviceStatus | '',
})

const typeOptions: Array<{ label: string; value: DeviceType }> = [
  { label: '无人机 UAV', value: 'UAV' },
  { label: '无人艇 USV', value: 'USV' },
  { label: '灯塔目标', value: 'LIGHTHOUSE' },
  { label: 'ROS 节点', value: 'ROS_NODE' },
  { label: 'Unity 节点', value: 'UNITY_NODE' },
]

const statusOptions: Array<{ label: string; value: DeviceStatus }> = [
  { label: '在线', value: 'ONLINE' },
  { label: '离线', value: 'OFFLINE' },
  { label: '维护中', value: 'MAINTENANCE' },
  { label: '未知', value: 'UNKNOWN' },
]

const controlLabels: Record<SimulationStatus, string> = {
  STARTING: '启动中',
  RUNNING: '运行中',
  PARTIAL: '部分在线',
  STOPPING: '停止中',
  STOPPED: '已停止',
  FAILED: '异常',
}

const onlineRate = computed(() => {
  const summary = monitoringStore.summary
  if (!summary?.totalNodes) return 0
  return Math.round((summary.onlineNodes / summary.totalNodes) * 100)
})

const canStart = computed(() => {
  const status = controlStore.runtime?.status
  return actionPhase.value === 'idle' && !controlStore.loading && (!status || status === 'STOPPED' || status === 'FAILED')
})

const isOperating = computed(() => actionPhase.value !== 'idle' || controlStore.loading)
const canStop = computed(() => {
  const status = controlStore.runtime?.status
  return actionPhase.value === 'idle' && !controlStore.loading && !!status && !['STOPPED', 'FAILED'].includes(status)
})
const operationText = computed(() => {
  if (actionPhase.value === 'starting') return '正在启动 ROS/Gazebo、WebSocket Bridge 和 Unity 联动，请等待真实心跳确认。'
  if (actionPhase.value === 'stopping') return '正在停止平台托管的 ROS/Gazebo 与 Unity 联动，请等待节点下线。'
  if (controlStore.runtime?.status === 'RUNNING') return '检测到仿真已经在运行，页面正在接入监控。'
  return ''
})

const rosNode = computed(() => monitoringStore.nodes.find((node) => node.type === 'ROS_NODE'))
const unityNode = computed(() => monitoringStore.nodes.find((node) => node.type === 'UNITY_NODE'))
const liveVehicleNodes = computed(() =>
  monitoringStore.nodes.filter(
    (node) =>
      ['UAV', 'USV'].includes(node.type) &&
      node.status === 'ONLINE' &&
      node.positionX !== null &&
      node.positionY !== null &&
      node.positionZ !== null,
  ),
)
const visibleCommandLogs = computed(() => controlStore.commands.slice(0, 4))
const pagedCommandLogs = computed(() => {
  const start = (commandLogPage.value - 1) * commandLogPageSize.value
  return controlStore.commands.slice(start, start + commandLogPageSize.value)
})

const diagnosticSteps = computed(() => [
  {
    key: 'ros',
    title: 'ROS / Gazebo',
    status: rosNode.value?.status === 'ONLINE' ? 'ONLINE' : 'OFFLINE',
    metric: rosNode.value?.status === 'ONLINE' ? 'WebSocket 已连接' : '等待 8765 位姿帧',
    detail: rosNode.value?.detail || '检查 WSL、Gazebo 和 uav_usv_unity_websocket_bridge.launch.py',
  },
  {
    key: 'backend',
    title: 'Spring Boot 接收',
    status: liveVehicleNodes.value.length > 0 ? 'ONLINE' : 'OFFLINE',
    metric: `${liveVehicleNodes.value.length} 个载体位姿`,
    detail:
      liveVehicleNodes.value.length > 0
        ? `已接收 ${liveVehicleNodes.value.map((node) => node.code).join(' / ')}`
        : '后端尚未收到 UAV / USV 的有效 Gazebo 坐标',
  },
  {
    key: 'vue',
    title: 'Vue 实时刷新',
    status: monitoringStore.error ? 'OFFLINE' : monitoringStore.summary ? 'ONLINE' : 'UNKNOWN',
    metric: monitoringStore.summary ? formatTime(monitoringStore.summary.refreshedAt) : '--',
    detail: monitoringStore.error || '监控接口与 SSE 刷新通道可用',
  },
  {
    key: 'unity',
    title: 'Unity WebGL 心跳',
    status: unityNode.value?.status === 'ONLINE' ? 'ONLINE' : 'OFFLINE',
    metric: unityNode.value?.status === 'ONLINE' ? 'WebGL 已上报' : '等待系统总览 WebGL',
    detail: unityNode.value?.detail || '进入系统总览并等待 UNITY WEBGL ONLINE',
  },
])

function typeLabel(type: DeviceType) {
  return typeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: DeviceStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function statusClass(status: DeviceStatus) {
  return status.toLowerCase()
}

function typeClass(type: DeviceType) {
  return type.toLowerCase().replace('_', '-')
}

function nodeInitial(type: DeviceType) {
  if (type === 'UAV') return 'UAV'
  if (type === 'USV') return 'USV'
  if (type === 'LIGHTHOUSE') return '灯塔'
  if (type === 'ROS_NODE') return 'ROS'
  if (type === 'UNITY_NODE') return '3D'
  return 'NODE'
}

function controlTag(status?: SimulationStatus) {
  if (status === 'RUNNING') return 'success'
  if (status === 'STARTING' || status === 'STOPPING' || status === 'PARTIAL') return 'warning'
  if (status === 'FAILED') return 'danger'
  return 'info'
}

function endpoint(row: RuntimeNode | Record<string, unknown>) {
  return (row as RuntimeNode).endpoint || '--'
}

function formatTime(value: string | null) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

function formatAge(seconds: number) {
  if (seconds < 0) return '--'
  if (seconds < 60) return `${seconds} 秒前`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`
  return `${Math.floor(seconds / 3600)} 小时前`
}

function formatPosition(row: RuntimeNode | Record<string, unknown>) {
  const node = row as RuntimeNode
  if (node.positionX == null || node.positionY == null || node.positionZ == null) return '--'
  return `${node.positionX.toFixed(2)}, ${node.positionY.toFixed(2)}, ${node.positionZ.toFixed(2)}`
}

function sourceLabel(source: string) {
  if (source === 'ROS_WEBSOCKET') return 'ROS / Gazebo'
  if (source === 'UNITY_HEARTBEAT') return 'Unity 心跳'
  return source || '--'
}

function commandTypeLabel(type: string) {
  const labels: Record<string, string> = {
    START: '运行',
    STOP: '停止',
    TAKEOFF: '起飞',
    LAND: '降落',
    START_MISSION: '开始任务',
    STOP_MISSION: '停止任务',
    PAUSE_MISSION: '暂停任务',
    RESUME_MISSION: '恢复任务',
    COMPLETE_MISSION: '完成任务',
    FAIL_MISSION: '异常终止',
    CANCEL_MISSION: '取消任务',
    SELECT_DEVICE: '选择设备',
    FOCUS_DEVICE: '聚焦设备',
    SWITCH_CAMERA: '切换视角',
    TOGGLE_TRAJECTORY: '轨迹显示',
  }
  return labels[type] ?? type
}

function commandStatusLabel(status: string) {
  if (status === 'ACKNOWLEDGED') return '已确认'
  if (status === 'DISPATCHED') return '已下发'
  if (status === 'FAILED') return '失败'
  if (status === 'TIMEOUT') return '确认超时'
  return '待处理'
}

function commandStatusClass(status: string) {
  return status.toLowerCase()
}

async function openCommandLogDialog() {
  await controlStore.refreshCommands()
  commandLogPage.value = 1
  commandLogDialogVisible.value = true
}

function handleCommandLogPageChange(page: number) {
  commandLogPage.value = page
}

function heartbeatClass(seconds: number) {
  if (seconds < 0) return 'unknown'
  if (seconds <= 5) return 'fresh'
  if (seconds <= 15) return 'stale'
  return 'lost'
}

function onlineNodeCount(type: DeviceType) {
  return monitoringStore.nodes.filter((node) => node.type === type && node.status === 'ONLINE').length
}

function latestHeartbeat(type: DeviceType) {
  const nodes = monitoringStore.nodes.filter((node) => node.type === type && node.lastHeartbeatAt)
  if (!nodes.length) return '--'
  const heartbeats = nodes.map((node) => node.lastHeartbeatAt).sort()
  return formatTime(heartbeats[heartbeats.length - 1] ?? null)
}

async function load() {
  monitoringStore.type = filters.type || undefined
  monitoringStore.status = filters.status || undefined
  await monitoringStore.refresh()
}

async function resetFilters() {
  filters.type = ''
  filters.status = ''
  await load()
}

async function startSimulation() {
  actionPhase.value = 'starting'
  try {
    await controlStore.start()
    if (controlStore.error) {
      ElMessage.error(controlStore.error)
      return
    }
    await waitForRuntimeStatus(['RUNNING', 'PARTIAL', 'FAILED'], 45000)
    await controlStore.refreshCommands()
    await monitoringStore.refresh()
    if (controlStore.runtime?.status === 'RUNNING') {
      ElMessage.success('仿真已运行，ROS / Unity 心跳已确认')
    } else if (controlStore.runtime?.status === 'PARTIAL') {
      ElMessage.warning(controlStore.runtime.message || '仿真部分启动，请查看联调诊断')
    } else {
      ElMessage.error(controlStore.runtime?.message || '启动失败')
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '启动状态确认失败')
  } finally {
    actionPhase.value = 'idle'
  }
}

async function stopSimulation() {
  actionPhase.value = 'stopping'
  try {
    await controlStore.stop()
    if (controlStore.error) {
      ElMessage.error(controlStore.error)
      return
    }

    await controlStore.refresh()
    await waitForRuntimeStatus(['STOPPED', 'FAILED'], 30000)
    await controlStore.refreshCommands()
    await monitoringStore.refresh()

    if (controlStore.runtime?.status === 'STOPPED') {
      ElMessage.success('仿真已停止，运行节点已下线')
    } else {
      ElMessage.error(controlStore.runtime?.message || '停止失败')
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '停止状态确认失败')
  } finally {
    await controlStore.refresh()
    actionPhase.value = 'idle'
  }
}

async function waitForRuntimeStatus(targetStatuses: SimulationStatus[], timeoutMs: number) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    await controlStore.refresh()
    await monitoringStore.refresh()
    if (controlStore.runtime && targetStatuses.includes(controlStore.runtime.status)) return
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
  throw new Error('运行状态确认超时，请查看 WSL 终端和联调诊断')
}

function handleRuntimeAction(action: 'start' | 'stop' | 'refresh', event: MouseEvent) {
  event.preventDefault()
  event.stopPropagation()

  if (action === 'start') void startSimulation()
  else if (action === 'stop') void stopSimulation()
  else void load()
}

function handleRuntimeActionCapture(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  const button = target?.closest<HTMLButtonElement>('button[data-runtime-action]')
  if (!button || button.disabled) return

  const action = button.dataset.runtimeAction
  if (action === 'start' || action === 'stop' || action === 'refresh') handleRuntimeAction(action, event)
}

onMounted(async () => {
  document.addEventListener('click', handleRuntimeActionCapture, true)
  await Promise.all([load(), controlStore.refresh(), controlStore.refreshCommands()])
  monitoringStore.connectEvents()
  controlTimer = window.setInterval(() => controlStore.refresh(), 2000)
  commandTimer = window.setInterval(() => controlStore.refreshCommands(), 5000)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleRuntimeActionCapture, true)
  monitoringStore.disconnectEvents()
  if (controlTimer !== null) window.clearInterval(controlTimer)
  if (commandTimer !== null) window.clearInterval(commandTimer)
})
</script>

<template>
  <ConsoleLayout title="运行监控" eyebrow="RUNTIME MONITOR" :show-refresh="false">
    <template #actions>
      <el-tag :type="controlTag(controlStore.runtime?.status)" effect="plain">
        {{ controlStore.runtime ? controlLabels[controlStore.runtime.status] : '状态未知' }}
      </el-tag>
      <button
        data-runtime-action="start"
        type="button"
        class="runtime-topbar-button primary"
        :disabled="!canStart"
        @click="handleRuntimeAction('start', $event)"
      >
        <Play :size="16" />
        {{ actionPhase === 'starting' ? '启动中...' : '运行' }}
      </button>
      <button
        v-if="canStop || actionPhase === 'stopping'"
        data-runtime-action="stop"
        type="button"
        class="runtime-topbar-button danger"
        :disabled="isOperating && actionPhase !== 'stopping'"
        @click="handleRuntimeAction('stop', $event)"
      >
        <Square :size="15" />
        {{ actionPhase === 'stopping' ? '停止中...' : '停止' }}
      </button>
      <button
        data-runtime-action="refresh"
        type="button"
        class="runtime-topbar-button"
        :disabled="monitoringStore.loading"
        @click="handleRuntimeAction('refresh', $event)"
      >
        <RefreshCw :size="16" />
        刷新
      </button>
    </template>

    <el-alert
      v-if="monitoringStore.error || controlStore.error"
      title="运行状态读取失败"
      :description="monitoringStore.error || controlStore.error"
      type="error"
      show-icon
      :closable="false"
      class="section-alert"
    />
    <el-alert v-if="operationText" :title="operationText" type="info" show-icon :closable="false" class="section-alert" />

    <section class="runtime-hero console-panel">
      <div>
        <span>RUNTIME LINK CONTROL</span>
        <strong>{{ controlStore.runtime ? controlLabels[controlStore.runtime.status] : '正在读取状态' }}</strong>
        <small>{{ controlStore.runtime?.message ?? '等待 ROS / Unity 心跳回传。' }}</small>
      </div>
      <div class="runtime-hero-metrics">
        <article><span>节点在线率</span><strong>{{ onlineRate }}%</strong></article>
        <article><span>ROS</span><strong :class="{ online: controlStore.runtime?.rosOnline }">{{ controlStore.runtime?.rosOnline ? '在线' : '离线' }}</strong></article>
        <article><span>Unity</span><strong :class="{ online: controlStore.runtime?.unityOnline }">{{ controlStore.runtime?.unityOnline ? '在线' : '离线' }}</strong></article>
        <article><span>告警</span><strong>{{ (monitoringStore.summary?.offlineNodes ?? 0) + (monitoringStore.summary?.unknownNodes ?? 0) }}</strong></article>
      </div>
    </section>

    <section class="page-metric-grid">
      <article class="console-stat-card">
        <span>UAV 在线</span>
        <strong>{{ onlineNodeCount('UAV') }}</strong>
        <small>{{ latestHeartbeat('UAV') }}</small>
      </article>
      <article class="console-stat-card">
        <span>USV 在线</span>
        <strong>{{ onlineNodeCount('USV') }}</strong>
        <small>{{ latestHeartbeat('USV') }}</small>
      </article>
      <article class="console-stat-card">
        <span>ROS Bridge 在线</span>
        <strong>{{ onlineNodeCount('ROS_NODE') }}</strong>
        <small>{{ latestHeartbeat('ROS_NODE') }}</small>
      </article>
      <article class="console-stat-card">
        <span>Unity 心跳</span>
        <strong>{{ onlineNodeCount('UNITY_NODE') }}</strong>
        <small>{{ latestHeartbeat('UNITY_NODE') }}</small>
      </article>
    </section>

    <section class="runtime-two-column">
      <article class="console-panel runtime-diagnostic">
        <div class="panel-heading">
          <div>
            <h2>联调诊断</h2>
            <p>按数据流检查 Gazebo、后端、前端刷新与 Unity WebGL 心跳。</p>
          </div>
          <el-tag effect="plain">{{ onlineRate }}% ONLINE</el-tag>
        </div>
        <div class="runtime-diagnostic-list">
          <article v-for="step in diagnosticSteps" :key="step.key" :class="step.status.toLowerCase()">
            <span>{{ step.title }}</span>
            <strong>{{ step.metric }}</strong>
            <small>{{ step.detail }}</small>
          </article>
        </div>
      </article>

      <article class="console-panel runtime-log">
        <div class="panel-heading">
          <div>
            <h2>实时日志</h2>
            <p>记录运行、停止和快捷指令的执行结果。</p>
          </div>
          <el-button link type="primary" @click="openCommandLogDialog">全部日志</el-button>
        </div>
        <div class="runtime-log-list">
          <el-empty v-if="controlStore.commands.length === 0" description="暂无控制指令记录" :image-size="56" />
          <article v-for="command in visibleCommandLogs" v-else :key="command.id">
            <span>{{ formatTime(command.completedAt || command.requestedAt) }} {{ commandTypeLabel(command.commandType) }}</span>
            <b :class="commandStatusClass(command.status)">{{ commandStatusLabel(command.status) }}</b>
          </article>
        </div>
      </article>
    </section>

    <section class="console-panel filter-panel">
      <el-select v-model="filters.type" clearable placeholder="节点类型">
        <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="运行状态">
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button type="primary" :icon="Search" :loading="monitoringStore.loading" @click="load">查询</el-button>
      <el-button :icon="RotateCcw" @click="resetFilters">重置</el-button>
    </section>

    <section class="console-panel table-panel">
      <div class="panel-heading">
        <div>
          <h2>实时节点</h2>
          <p>状态由 ROS WebSocket 数据和 Unity 心跳共同确认。</p>
        </div>
        <el-tag effect="plain">更新 {{ formatTime(monitoringStore.summary?.refreshedAt ?? null) }}</el-tag>
      </div>

      <el-table v-loading="monitoringStore.loading" :data="monitoringStore.nodes" class="console-table">
        <el-table-column label="节点" min-width="220">
          <template #default="{ row }">
            <div class="asset-name-cell">
              <span class="asset-mini-mark" :class="typeClass(row.type)">{{ nodeInitial(row.type) }}</span>
              <div>
                <strong>{{ row.name }}</strong>
                <small>{{ row.code }}</small>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" min-width="130">
          <template #default="{ row }">{{ typeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ONLINE' ? 'success' : row.status === 'OFFLINE' ? 'danger' : 'warning'" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最新数据" min-width="210">
          <template #default="{ row }">{{ formatPosition(row) }}</template>
        </el-table-column>
        <el-table-column label="心跳" min-width="130">
          <template #default="{ row }">
            <span class="heartbeat-pill" :class="heartbeatClass(row.heartbeatAgeSeconds)">{{ formatAge(row.heartbeatAgeSeconds) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="140">
          <template #default="{ row }">{{ sourceLabel(row.source) }}</template>
        </el-table-column>
        <el-table-column label="端点" min-width="180">
          <template #default="{ row }">{{ endpoint(row) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="commandLogDialogVisible" title="控制指令日志" width="860px" class="runtime-command-log-dialog">
      <div class="runtime-command-log-dialog-list">
        <el-empty v-if="controlStore.commands.length === 0" description="暂无控制指令记录" :image-size="72" />
        <template v-else>
          <article
            v-for="command in pagedCommandLogs"
            :key="command.id"
            class="runtime-command-log-detail"
            :class="commandStatusClass(command.status)"
          >
            <div class="runtime-command-log-detail-head">
              <div>
                <strong>{{ commandTypeLabel(command.commandType) }}</strong>
                <span>#{{ command.id }} / {{ command.commandType }}</span>
              </div>
              <b :class="commandStatusClass(command.status)">{{ commandStatusLabel(command.status) }}</b>
            </div>
            <dl class="runtime-command-log-detail-grid">
              <div><dt>执行人</dt><dd>{{ command.requestedBy || 'system' }}</dd></div>
              <div><dt>提交时间</dt><dd>{{ formatTime(command.requestedAt) }}</dd></div>
              <div><dt>下发时间</dt><dd>{{ formatTime(command.dispatchedAt) }}</dd></div>
              <div><dt>确认时间</dt><dd>{{ formatTime(command.acknowledgedAt) }}</dd></div>
              <div><dt>会话 ID</dt><dd>{{ command.sessionId ?? '--' }}</dd></div>
              <div><dt>任务批次</dt><dd>{{ command.runId ?? '--' }}</dd></div>
              <div><dt>目标设备</dt><dd>{{ command.deviceId ?? '--' }}</dd></div>
              <div><dt>指令编号</dt><dd :title="command.commandKey">{{ command.commandKey }}</dd></div>
              <div><dt>错误码</dt><dd>{{ command.errorCode ?? '--' }}</dd></div>
            </dl>
            <p>{{ command.detail || '指令已记录，等待执行结果' }}</p>
          </article>
        </template>
      </div>
      <template #footer>
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="controlStore.commands.length"
          :current-page="commandLogPage"
          :page-size="commandLogPageSize"
          @current-change="handleCommandLogPageChange"
        />
      </template>
    </el-dialog>
  </ConsoleLayout>
</template>
