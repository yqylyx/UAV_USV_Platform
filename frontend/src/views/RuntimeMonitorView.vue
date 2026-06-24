<script setup lang="ts">
import { Activity, Plane, Play, Radar, RefreshCw, RotateCcw, Search, Ship, Square } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, reactive } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { useRuntimeControlStore } from '@/stores/runtimeControl'
import type { DeviceStatus, DeviceType } from '@/types/device'
import type { RuntimeNode } from '@/types/monitoring'
import type { SimulationStatus } from '@/types/runtimeControl'

const monitoringStore = useMonitoringStore()
const controlStore = useRuntimeControlStore()
let controlTimer: number | null = null

const filters = reactive({
  type: '' as DeviceType | '',
  status: '' as DeviceStatus | '',
})

const typeOptions: Array<{ label: string; value: DeviceType }> = [
  { label: '无人机 UAV', value: 'UAV' },
  { label: '无人艇 USV', value: 'USV' },
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
  return !controlStore.loading && (!status || status === 'STOPPED' || status === 'FAILED')
})

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
  await controlStore.start()
  await monitoringStore.refresh()
}

async function stopSimulation() {
  await controlStore.stop()
  await monitoringStore.refresh()
}

onMounted(async () => {
  await Promise.all([load(), controlStore.refresh()])
  monitoringStore.connectEvents()
  controlTimer = window.setInterval(() => controlStore.refresh(), 2000)
})

onBeforeUnmount(() => {
  monitoringStore.disconnectEvents()
  if (controlTimer !== null) window.clearInterval(controlTimer)
})
</script>

<template>
  <ConsoleLayout title="运行监控" eyebrow="RUNTIME MONITOR">
    <template #actions>
      <el-tag :type="controlTag(controlStore.runtime?.status)" effect="plain">
        {{ controlStore.runtime ? controlLabels[controlStore.runtime.status] : '状态未知' }}
      </el-tag>
      <el-button type="primary" :icon="Play" :loading="controlStore.loading" :disabled="!canStart" @click="startSimulation">
        运行
      </el-button>
      <el-button
        v-if="controlStore.runtime?.controllable"
        type="danger"
        plain
        :icon="Square"
        :loading="controlStore.loading"
        @click="stopSimulation"
      >
        停止
      </el-button>
      <el-button :loading="monitoringStore.loading" :icon="RefreshCw" @click="load">刷新</el-button>
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

    <section class="runtime-command" aria-label="仿真运行状态">
      <div class="runtime-command-main">
        <p>RUNTIME LINK CONTROL</p>
        <h2>{{ controlStore.runtime ? controlLabels[controlStore.runtime.status] : '正在读取运行状态' }}</h2>
        <span>{{ controlStore.runtime?.message ?? '正在连接运行控制服务，等待 ROS / Unity 心跳回传。' }}</span>
      </div>
      <div class="runtime-command-state">
        <div>
          <span class="runtime-status-dot" :class="controlStore.runtime?.status?.toLowerCase()" />
          <strong>{{ onlineRate }}%</strong>
          <small>节点在线率</small>
        </div>
        <div>
          <span>ROS</span>
          <strong :class="{ online: controlStore.runtime?.rosOnline }">{{ controlStore.runtime?.rosOnline ? '在线' : '离线' }}</strong>
          <small>Gazebo 数据链路</small>
        </div>
        <div>
          <span>Unity</span>
          <strong :class="{ online: controlStore.runtime?.unityOnline }">{{ controlStore.runtime?.unityOnline ? '在线' : '离线' }}</strong>
          <small>三维态势心跳</small>
        </div>
      </div>
    </section>

    <section class="runtime-tactical-grid" aria-label="运行状态指标">
      <article class="runtime-tactical-card">
        <div class="runtime-card-head">
          <span>在线节点</span>
          <b>{{ monitoringStore.summary?.onlineNodes ?? 0 }} / {{ monitoringStore.summary?.totalNodes ?? 0 }}</b>
        </div>
        <div class="runtime-progress-bar"><i :style="{ width: `${onlineRate}%` }"></i></div>
        <p>实时心跳确认的 ROS、Unity、UAV 与 USV 节点。</p>
      </article>
      <article class="runtime-tactical-card">
        <div class="runtime-card-head">
          <span>通信 / 可视化</span>
          <b>{{ monitoringStore.summary?.rosNodes ?? 0 }} / {{ monitoringStore.summary?.unityNodes ?? 0 }}</b>
        </div>
        <p>ROS WebSocket 与 Unity 心跳共同构成仿真到可视化链路。</p>
      </article>
      <article class="runtime-tactical-card">
        <div class="runtime-card-head">
          <span>协同载体</span>
          <b>{{ monitoringStore.summary?.vehicleNodes ?? 0 }}</b>
        </div>
        <p>无人机和无人艇作为围捕任务的执行单元。</p>
      </article>
      <article class="runtime-tactical-card attention">
        <div class="runtime-card-head">
          <span>异常关注</span>
          <b>{{ (monitoringStore.summary?.offlineNodes ?? 0) + (monitoringStore.summary?.unknownNodes ?? 0) }}</b>
        </div>
        <p>离线、未知或长时间未收到心跳的节点需要优先排查。</p>
      </article>
    </section>

    <section class="runtime-node-grid" aria-label="节点类型状态">
      <article class="runtime-node-card">
        <div class="node-card-icon uav"><Plane :size="20" /></div>
        <div><span>UAV 在线</span><strong>{{ onlineNodeCount('UAV') }}</strong><small>{{ latestHeartbeat('UAV') }}</small></div>
      </article>
      <article class="runtime-node-card">
        <div class="node-card-icon usv"><Ship :size="20" /></div>
        <div><span>USV 在线</span><strong>{{ onlineNodeCount('USV') }}</strong><small>{{ latestHeartbeat('USV') }}</small></div>
      </article>
      <article class="runtime-node-card">
        <div class="node-card-icon ros"><Radar :size="20" /></div>
        <div><span>ROS bridge 在线</span><strong>{{ onlineNodeCount('ROS_NODE') }}</strong><small>{{ latestHeartbeat('ROS_NODE') }}</small></div>
      </article>
      <article class="runtime-node-card">
        <div class="node-card-icon unity"><Activity :size="20" /></div>
        <div><span>Unity 在线</span><strong>{{ onlineNodeCount('UNITY_NODE') }}</strong><small>{{ latestHeartbeat('UNITY_NODE') }}</small></div>
      </article>
    </section>

    <section class="device-filter-panel runtime-filter" aria-label="运行节点筛选">
      <div class="runtime-filter-fields">
        <el-select v-model="filters.type" clearable placeholder="节点类型">
          <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="运行状态">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>
      <div class="runtime-filter-actions">
        <el-button type="primary" :icon="Search" :loading="monitoringStore.loading" @click="load">查询</el-button>
        <el-button :icon="RotateCcw" @click="resetFilters">重置</el-button>
      </div>
    </section>

    <section class="runtime-live-section">
      <div class="section-heading">
        <div>
          <h2>实时节点</h2>
          <p>状态由 ROS WebSocket 数据和 Unity 心跳共同确认。</p>
        </div>
        <el-tag effect="plain">更新 {{ formatTime(monitoringStore.summary?.refreshedAt ?? null) }}</el-tag>
      </div>

      <div v-loading="monitoringStore.loading" class="runtime-live-grid">
        <el-empty v-if="!monitoringStore.loading && monitoringStore.nodes.length === 0" description="暂无运行节点" />
        <template v-else>
          <article
            v-for="node in monitoringStore.nodes"
            :key="node.id"
            class="runtime-live-card"
            :class="[typeClass(node.type), statusClass(node.status)]"
          >
            <div class="runtime-live-top">
              <div class="runtime-live-mark" :class="typeClass(node.type)">{{ nodeInitial(node.type) }}</div>
              <div>
                <strong>{{ node.name }}</strong>
                <span>{{ node.code }}</span>
              </div>
              <i class="runtime-live-dot" :class="statusClass(node.status)"></i>
            </div>
            <div class="runtime-live-status">
              <span>{{ statusLabel(node.status) }}</span>
              <b :class="heartbeatClass(node.heartbeatAgeSeconds)">{{ formatAge(node.heartbeatAgeSeconds) }}</b>
            </div>
            <div class="runtime-live-body">
              <div><span>数据来源</span><strong>{{ sourceLabel(node.source) }}</strong></div>
              <div><span>IP / 端口</span><strong>{{ endpoint(node) }}</strong></div>
              <div><span>Gazebo 坐标</span><strong>{{ formatPosition(node) }}</strong></div>
              <div><span>最后心跳</span><strong>{{ formatTime(node.lastHeartbeatAt) }}</strong></div>
            </div>
            <p class="runtime-live-detail">{{ node.detail || '暂无附加运行详情' }}</p>
          </article>
        </template>
      </div>
    </section>
  </ConsoleLayout>
</template>
