<script setup lang="ts">
import { computed } from 'vue'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'
import { getAlgorithmMissionPreview } from '@/services/algorithmMissionDataService'
import type {
  AlgorithmMissionType,
  AlgorithmVehicleType,
} from '@/types/algorithmMission'

const { selectedMissionType } = useAlgorithmMissionDemo()

const preview = computed(() =>
  getAlgorithmMissionPreview(selectedMissionType.value),
)

function missionTypeLabel(type: AlgorithmMissionType) {
  return type === 'CAPTURE' ? '协同围捕' : '护航防守'
}

function vehicleTypeLabel(type: AlgorithmVehicleType) {
  return type === 'UAV' ? '无人机' : '无人艇'
}

function eventTagType(level: string) {
  if (level === 'SUCCESS') return 'success'
  if (level === 'WARNING') return 'warning'
  if (level === 'ERROR') return 'danger'
  return 'info'
}

function eventLevelLabel(level: string) {
  if (level === 'SUCCESS') return '完成'
  if (level === 'WARNING') return '告警'
  if (level === 'ERROR') return '错误'
  return '信息'
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
        <p>展示围捕与护航防守算法的阶段、角色分配和运行事件。</p>
      </div>

      <div class="algorithm-heading-actions">
        <el-radio-group v-model="selectedMissionType">
          <el-radio-button value="CAPTURE">协同围捕</el-radio-button>
          <el-radio-button value="ESCORT_DEFENSE">护航防守</el-radio-button>
        </el-radio-group>

        <el-tag effect="plain">演示数据</el-tag>
      </div>
    </div>

    <div class="algorithm-summary">
      <article>
        <span>任务模式</span>
        <strong>{{ missionTypeLabel(preview.summary.missionType) }}</strong>
      </article>

      <article>
        <span>当前阶段</span>
        <strong>{{ preview.summary.statusName }}</strong>
      </article>

      <article>
        <span>任务目标</span>
        <strong>{{ preview.summary.targetId }}</strong>
      </article>

      <article>
        <span>参与平台</span>
        <strong>
          {{ preview.summary.participatingUavs }} UAV /
          {{ preview.summary.participatingUsvs }} USV
        </strong>
      </article>
    </div>

    <div class="algorithm-progress">
      <div>
        <strong>{{ preview.summary.algorithmName }}</strong>
        <span>已运行 {{ preview.summary.elapsedSeconds }} 秒</span>
      </div>

      <el-progress
        :percentage="preview.summary.progress"
        :stroke-width="12"
      />

      <p>{{ preview.summary.detail }}</p>
    </div>

    <div class="algorithm-content">
      <article class="assignment-section">
        <div class="subsection-heading">
          <div>
            <h3>角色与目标分配</h3>
            <p>展示算法为各UAV和USV生成的任务位置。</p>
          </div>
          <el-tag effect="plain">
            {{ preview.assignments.length }}个平台
          </el-tag>
        </div>

        <el-table :data="preview.assignments">
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
            <p>显示算法阶段变化。</p>
          </div>
        </div>

        <div class="algorithm-event-list">
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