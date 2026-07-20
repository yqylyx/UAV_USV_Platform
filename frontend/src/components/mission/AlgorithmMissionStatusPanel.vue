<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'
import { useAlgorithmStore } from '@/stores/algorithm'
import type {
  AlgorithmAssignmentRole,
  AlgorithmEventLevel,
  AlgorithmRunStatus,
} from '@/api/algorithm'
import type { AlgorithmMissionType } from '@/types/algorithmMission'

const {
  currentCommandId,
  selectedMissionType,
  captureForm,
  escortForm,
  submittedPositionSource,
  submittedVehicleIds,
} = useAlgorithmMissionDemo()
const algorithmStore = useAlgorithmStore()

const runs = computed(() => algorithmStore.runs)
const activeRun = computed(() => algorithmStore.activeRun)
const latestRun = computed(() => algorithmStore.latestRun)
const assignments = computed(() => algorithmStore.assignments)
const events = computed(() => algorithmStore.events)
const loading = computed(() => algorithmStore.loading)
const error = computed(() => algorithmStore.error)

const currentRun = computed(() => {
  const commandId = currentCommandId.value
  if (!commandId) return null
  return (
    runs.value.find((run) => run.commandId === commandId) ??
    (activeRun.value?.commandId === commandId ? activeRun.value : null) ??
    (latestRun.value?.commandId === commandId ? latestRun.value : null)
  )
})

const currentAssignments = computed(() => {
  if (!currentCommandId.value || assignments.value?.commandId !== currentCommandId.value) {
    return []
  }
  return assignments.value.assignments
})

const currentEvents = computed(() =>
  currentCommandId.value
    ? events.value.filter((event) => event.commandId === currentCommandId.value)
    : [],
)

const selectedVehicleCount = computed(() => {
  const form = selectedMissionType.value === 'CAPTURE' ? captureForm : escortForm
  return form.uavIds.length + form.usvIds.length
})

const resultSourceLabel = computed(() =>
  submittedPositionSource.value === 'MANUAL' ? '手动初始位姿实验' : '实时位姿',
)

const resultSourceDescription = computed(() =>
  submittedPositionSource.value === 'MANUAL'
    ? '车辆初始位置来自人工输入；任务分配与事件来自真实Python算法服务。'
    : '车辆初始位置来自 RuntimeDeviceStatus；任务分配与事件来自真实Python算法服务。',
)

const pollingStatuses = new Set<AlgorithmRunStatus>(['PENDING', 'RUNNING'])
let pollingTimer: ReturnType<typeof setInterval> | null = null
let refreshing = false
let queuedCommandId: string | null = null

function shouldPoll(status?: AlgorithmRunStatus | null) {
  return !!status && pollingStatuses.has(status)
}

function clearPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

async function refreshCurrentAlgorithm(commandId: string) {
  if (refreshing) {
    queuedCommandId = commandId
    return
  }

  refreshing = true
  try {
    await Promise.all([
      algorithmStore.refreshStatus(commandId),
      algorithmStore.refreshAssignments(commandId),
      algorithmStore.refreshEvents(commandId),
    ])
  } finally {
    refreshing = false
    const nextCommandId = queuedCommandId
    queuedCommandId = null
    if (nextCommandId && nextCommandId === currentCommandId.value) {
      void refreshCurrentAlgorithm(nextCommandId)
    }
  }
}

function ensurePolling() {
  if (!currentCommandId.value || !shouldPoll(currentRun.value?.status)) {
    clearPolling()
    return
  }

  if (pollingTimer !== null) return

  pollingTimer = setInterval(() => {
    const commandId = currentCommandId.value
    if (!commandId || !shouldPoll(currentRun.value?.status)) {
      clearPolling()
      return
    }
    void refreshCurrentAlgorithm(commandId)
  }, 3000)
}

watch(
  currentCommandId,
  (commandId) => {
    clearPolling()
    queuedCommandId = null
    if (!commandId) return

    void refreshCurrentAlgorithm(commandId).finally(() => {
      if (currentCommandId.value === commandId) {
        ensurePolling()
      }
    })
  },
  { immediate: true },
)

watch(
  () => currentRun.value?.status,
  () => {
    ensurePolling()
  },
)

onBeforeUnmount(() => {
  clearPolling()
  queuedCommandId = null
})

function missionTypeLabel(type: AlgorithmMissionType) {
  return type === 'CAPTURE' ? '协同围捕' : '护航防守'
}

function runStatusLabel(status?: AlgorithmRunStatus | null) {
  if (status === 'PENDING') return '等待算法处理'
  if (status === 'RUNNING') return '算法执行中'
  if (status === 'COMPLETED') return '算法已完成'
  if (status === 'FAILED') return '算法执行失败'
  if (status === 'TIMEOUT') return '算法执行超时'
  if (status === 'STOPPED') return '算法已停止'
  return '等待状态刷新'
}

function runStatusTagType(status?: AlgorithmRunStatus | null) {
  if (error.value) return 'danger'
  if (status === 'COMPLETED') return 'success'
  if (status === 'FAILED' || status === 'TIMEOUT') return 'danger'
  if (status === 'RUNNING') return 'success'
  if (status === 'STOPPED') return 'info'
  return 'warning'
}

function assignmentRoleLabel(role?: AlgorithmAssignmentRole | null) {
  if (role === 'TRACK') return '跟踪'
  if (role === 'INTERCEPT') return '拦截'
  if (role === 'ENCIRCLE') return '围捕'
  if (role === 'ESCORT') return '护航'
  if (role === 'DEFEND') return '防守'
  if (role === 'RETURN') return '返航'
  if (role === 'STANDBY') return '待命'
  return '--'
}

function eventTagType(level: string | AlgorithmEventLevel) {
  if (level === 'SUCCESS') return 'success'
  if (level === 'WARNING' || level === 'WARN') return 'warning'
  if (level === 'ERROR') return 'danger'
  return 'info'
}

function eventLevelLabel(level: string | AlgorithmEventLevel) {
  if (level === 'SUCCESS') return '完成'
  if (level === 'WARNING' || level === 'WARN') return '告警'
  if (level === 'ERROR') return '错误'
  return '信息'
}

function formatDateTime(value?: string | null) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatNullableNumber(value?: number | null) {
  return typeof value === 'number' ? value.toFixed(1) : '--'
}
</script>

<template>
  <section class="console-panel algorithm-mission-panel">
    <div class="algorithm-heading">
      <div>
        <h2>协同算法展示</h2>
        <p>展示围捕与护航防守算法的后端指令状态、任务分配和运行事件。</p>
      </div>

      <div class="algorithm-heading-actions">
        <el-radio-group v-model="selectedMissionType">
          <el-radio-button value="CAPTURE">协同围捕</el-radio-button>
          <el-radio-button value="ESCORT_DEFENSE">护航防守</el-radio-button>
        </el-radio-group>

        <el-tag v-if="currentCommandId" :type="runStatusTagType(currentRun?.status)" effect="plain">
          {{ loading ? '同步中' : runStatusLabel(currentRun?.status) }}
        </el-tag>
        <el-tag v-else effect="plain">尚未获得算法结果</el-tag>
      </div>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="demo-alert"
    />

    <template v-if="currentCommandId">
      <div class="algorithm-summary">
        <article>
          <span>任务模式</span>
          <strong>{{ currentRun ? missionTypeLabel(currentRun.algorithmType) : missionTypeLabel(selectedMissionType) }}</strong>
        </article>

        <article>
          <span>后端状态</span>
          <strong>{{ runStatusLabel(currentRun?.status) }}</strong>
        </article>

        <article>
          <span>输入来源</span>
          <strong>{{ resultSourceLabel }}</strong>
        </article>

        <article>
          <span>算法指令</span>
          <strong>{{ currentCommandId }}</strong>
        </article>

        <article>
          <span>任务目标</span>
          <strong>{{ currentRun?.targetId || assignments?.targetId || '--' }}</strong>
        </article>
      </div>

      <div class="algorithm-progress">
        <div>
          <strong>{{ currentRun?.stage || '等待阶段信息' }}</strong>
          <span>{{ formatDateTime(currentRun?.startedAt) }}</span>
        </div>

        <p>{{ currentRun?.message || '暂无后端状态消息' }}</p>
        <p>{{ resultSourceDescription }}</p>
        <p>提交车辆：{{ submittedVehicleIds.length }} 个</p>
        <p v-if="currentRun?.errorMessage">{{ currentRun.errorMessage }}</p>
      </div>
    </template>

    <template v-else>
      <div class="algorithm-summary">
        <article>
          <span>真实状态</span>
          <strong>尚未提交算法指令</strong>
        </article>

        <article>
          <span>当前任务模式</span>
          <strong>{{ missionTypeLabel(selectedMissionType) }}</strong>
        </article>

        <article>
          <span>算法结果</span>
          <strong>尚未获得算法结果</strong>
        </article>

        <article>
          <span>当前选择平台</span>
          <strong>{{ selectedVehicleCount }} 个</strong>
        </article>
      </div>

      <div class="algorithm-progress">
        <div>
          <strong>尚未获得算法结果</strong>
          <span>启动后显示真实Python算法结果</span>
        </div>

        <p>当前没有成功提交的算法结果；任务分配与事件只会在后端返回真实Python算法结果后显示。</p>
      </div>
    </template>

    <div class="algorithm-content">
      <article class="assignment-section">
        <div class="subsection-heading">
          <div>
            <h3>角色与目标分配</h3>
            <p>{{ currentCommandId ? '展示真实Python算法服务返回的任务分配结果。' : '尚未获得算法分配结果。' }}</p>
          </div>
          <el-tag effect="plain">
            {{ currentCommandId ? `${currentAssignments.length}个平台` : '尚未获得结果' }}
          </el-tag>
        </div>

        <el-table v-if="currentCommandId" :data="currentAssignments">
          <el-table-column prop="vehicleId" label="平台" min-width="100" />

          <el-table-column prop="vehicleCode" label="平台编号" min-width="110">
            <template #default="{ row }">
              {{ row.vehicleCode || '--' }}
            </template>
          </el-table-column>

          <el-table-column label="角色" min-width="110">
            <template #default="{ row }">
              {{ assignmentRoleLabel(row.role) }}
            </template>
          </el-table-column>

          <el-table-column label="目标位置" min-width="160">
            <template #default="{ row }">
              ({{ formatNullableNumber(row.x) }},
              {{ formatNullableNumber(row.y) }},
              {{ formatNullableNumber(row.z) }})
            </template>
          </el-table-column>

          <el-table-column label="航向" min-width="90">
            <template #default="{ row }">
              {{ formatNullableNumber(row.heading) }}
            </template>
          </el-table-column>

          <el-table-column prop="detail" label="详情" min-width="150">
            <template #default="{ row }">
              {{ row.detail || '--' }}
            </template>
          </el-table-column>

          <template #empty>
            暂无后端任务分配结果
          </template>
        </el-table>

        <el-empty
          v-else
          description="尚未获得算法结果"
          :image-size="90"
        />
      </article>

      <aside class="algorithm-event-section">
        <div class="subsection-heading">
          <div>
            <h3>运行事件</h3>
            <p>{{ currentCommandId ? '显示真实Python算法服务返回的事件。' : '尚未获得算法事件。' }}</p>
          </div>
        </div>

        <div v-if="currentCommandId" class="algorithm-event-list">
          <article
            v-for="event in currentEvents"
            :key="`${event.occurredAt}-${event.message}`"
            class="algorithm-event"
          >
            <div>
              <el-tag :type="eventTagType(event.level)" effect="plain">
                {{ eventLevelLabel(event.level) }}
              </el-tag>
              <time>{{ formatDateTime(event.occurredAt) }}</time>
            </div>
            <strong>{{ event.stage || '--' }}</strong>
            <p>{{ event.message }}</p>
          </article>

          <el-empty
            v-if="currentEvents.length === 0"
            description="暂无后端算法事件"
            :image-size="80"
          />
        </div>

        <el-empty
          v-else
          description="尚未获得算法结果"
          :image-size="80"
        />
      </aside>
    </div>
  </section>
</template>

<style scoped>
.algorithm-mission-panel {
  margin-bottom: 20px;
  overflow: hidden;
}

.algorithm-heading,
.subsection-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.algorithm-heading {
  margin-bottom: 18px;
}

.algorithm-heading h2,
.subsection-heading h3 {
  margin: 0;
}

.algorithm-heading h2 {
  font-size: 18px;
}

.subsection-heading h3 {
  font-size: 16px;
}

.algorithm-heading p,
.subsection-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.algorithm-heading-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.demo-alert {
  margin-bottom: 18px;
}

.algorithm-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.algorithm-summary article {
  padding: 14px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 8px;
  background: rgba(8, 35, 40, 0.45);
}

.algorithm-summary span,
.algorithm-summary strong {
  display: block;
}

.algorithm-summary span {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.algorithm-summary strong {
  overflow: hidden;
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.algorithm-progress {
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 8px;
}

.algorithm-progress > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.algorithm-progress span,
.algorithm-progress p {
  color: var(--el-text-color-secondary);
}

.algorithm-progress p {
  margin: 10px 0 0;
  font-size: 13px;
}

.algorithm-content {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 0.8fr);
  gap: 16px;
}

.assignment-section,
.algorithm-event-section {
  min-width: 0;
  padding: 16px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 8px;
}

.assignment-section .subsection-heading,
.algorithm-event-section .subsection-heading {
  margin-bottom: 14px;
}

.algorithm-event-list {
  display: grid;
  gap: 10px;
}

.algorithm-event {
  padding: 12px;
  border-left: 3px solid rgba(86, 207, 225, 0.7);
  border-radius: 4px;
  background: rgba(8, 35, 40, 0.45);
}

.algorithm-event > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.algorithm-event time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.algorithm-event strong {
  font-size: 14px;
}

.algorithm-event p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .algorithm-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .algorithm-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .algorithm-heading,
  .algorithm-heading-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .algorithm-summary {
    grid-template-columns: 1fr;
  }
}
</style>
