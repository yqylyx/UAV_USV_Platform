<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'
import { getAlgorithmMissionPreview } from '@/services/algorithmMissionDataService'
import { useAlgorithmStore } from '@/stores/algorithm'
import type {
  AlgorithmAssignmentRole,
  AlgorithmEventLevel,
  AlgorithmRunStatus,
} from '@/api/algorithm'
import type {
  AlgorithmMissionType,
  AlgorithmVehicleType,
} from '@/types/algorithmMission'

const { currentCommandId, selectedMissionType } = useAlgorithmMissionDemo()
const algorithmStore = useAlgorithmStore()

const runs = computed(() => algorithmStore.runs)
const activeRun = computed(() => algorithmStore.activeRun)
const latestRun = computed(() => algorithmStore.latestRun)
const assignments = computed(() => algorithmStore.assignments)
const events = computed(() => algorithmStore.events)
const loading = computed(() => algorithmStore.loading)
const error = computed(() => algorithmStore.error)

const preview = computed(() =>
  getAlgorithmMissionPreview(selectedMissionType.value),
)

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

function vehicleTypeLabel(type: AlgorithmVehicleType) {
  return type === 'UAV' ? '无人机' : '无人艇'
}

function runStatusLabel(status?: AlgorithmRunStatus | null) {
  if (status === 'PENDING') return '等待算法ACK'
  if (status === 'RUNNING') return '算法运行中'
  if (status === 'COMPLETED') return '算法已完成'
  if (status === 'FAILED') return '算法执行失败'
  if (status === 'TIMEOUT') return '算法ACK超时'
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

function formatCoordinate(value: number) {
  return value.toFixed(1)
}

function formatCost(value: number) {
  return value.toFixed(2)
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
        <el-tag v-else effect="plain">演示预览</el-tag>
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
          <span>演示模式</span>
          <strong>{{ missionTypeLabel(preview.summary.missionType) }}</strong>
        </article>

        <article>
          <span>演示目标</span>
          <strong>{{ preview.summary.targetId }}</strong>
        </article>

        <article>
          <span>演示平台</span>
          <strong>
            {{ preview.summary.participatingUavs }} UAV /
            {{ preview.summary.participatingUsvs }} USV
          </strong>
        </article>
      </div>

      <div class="algorithm-progress">
        <div>
          <strong>演示预览</strong>
          <span>非真实算法状态</span>
        </div>

        <p>下方任务分配和事件用于界面预览，不代表后端算法运行结果。</p>
      </div>
    </template>

    <div class="algorithm-content">
      <article class="assignment-section">
        <div class="subsection-heading">
          <div>
            <h3>角色与目标分配</h3>
            <p>{{ currentCommandId ? '展示后端返回的任务分配结果。' : '演示预览数据，非真实算法结果。' }}</p>
          </div>
          <el-tag effect="plain">
            {{ currentCommandId ? `${currentAssignments.length}个平台` : '演示预览' }}
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

        <el-table v-else :data="preview.assignments">
          <el-table-column prop="vehicleId" label="平台" min-width="100" />

          <el-table-column label="类型" min-width="90">
            <template #default="{ row }">
              {{ vehicleTypeLabel(row.vehicleType) }}
            </template>
          </el-table-column>

          <el-table-column prop="roleName" label="角色" min-width="120" />

          <el-table-column prop="targetId" label="任务目标" min-width="130" />

          <el-table-column label="目标位置" min-width="140">
            <template #default="{ row }">
              ({{ formatCoordinate(row.targetX) }},
              {{ formatCoordinate(row.targetY) }})
            </template>
          </el-table-column>

          <el-table-column label="分配代价" min-width="100">
            <template #default="{ row }">
              {{ formatCost(row.assignmentCost) }}
            </template>
          </el-table-column>

          <el-table-column prop="status" label="执行状态" min-width="150" />
        </el-table>
      </article>

      <aside class="algorithm-event-section">
        <div class="subsection-heading">
          <div>
            <h3>运行事件</h3>
            <p>{{ currentCommandId ? '显示后端算法事件。' : '演示预览事件，非真实算法结果。' }}</p>
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

        <div v-else class="algorithm-event-list">
          <article
            v-for="event in preview.events"
            :key="event.id"
            class="algorithm-event"
          >
            <div>
              <el-tag :type="eventTagType(event.level)" effect="plain">
                {{ eventLevelLabel(event.level) }}
              </el-tag>
              <time>{{ event.time }}</time>
            </div>
            <strong>{{ event.stage }}</strong>
            <p>{{ event.message }}</p>
          </article>
        </div>
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
