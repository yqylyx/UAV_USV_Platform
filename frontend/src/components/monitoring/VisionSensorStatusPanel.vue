<script setup lang="ts">

import { getVisionSensorStatuses } from '@/services/visionDataService'
import type { VisionSensorStatus } from '@/types/vision'

const sensors = getVisionSensorStatuses()

function sensorTypeLabel(type: VisionSensorStatus['sensorType']) {
  return type === 'CAMERA' ? '相机' : '激光雷达'
}

function statusLabel(
  online: boolean | null,
  healthy: boolean | null,
) {
  if (online === null) return '未接入'
  if (!online) return '离线'
  return healthy ? '正常' : '异常'
}

function statusTagType(
  online: boolean | null,
  healthy: boolean | null,
) {
  if (online === null) return 'info'
  if (!online) return 'danger'
  return healthy ? 'success' : 'warning'
}

function tfLabel(tfAvailable: boolean | null) {
  if (tfAvailable === null) return '--'
  return tfAvailable ? '正常' : '异常'
}

function tfTagType(tfAvailable: boolean | null) {
  if (tfAvailable === null) return 'info'
  return tfAvailable ? 'success' : 'warning'
}

function formatNumber(value: number | null, unit: string) {
  return value === null ? '--' : `${value} ${unit}`
}
</script>

<template>
  <section class="console-panel vision-sensor-panel">
    <div class="vision-sensor-heading">
      <div>
        <h2>视觉传感器状态</h2>
        <p>监控相机与激光雷达的数据频率、延迟和 TF 状态。</p>
      </div>
      <el-tag effect="plain">静态预览</el-tag>
    </div>

    <el-table :data="sensors" class="vision-sensor-table">
      <el-table-column prop="vehicleId" label="载具编号" min-width="120" />

      <el-table-column prop="sensorId" label="传感器编号" min-width="150" />

      <el-table-column label="传感器类型" min-width="130">
        <template #default="{ row }">
          {{ sensorTypeLabel(row.sensorType) }}
        </template>
      </el-table-column>

      <el-table-column label="运行状态" min-width="110">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.online, row.healthy)" effect="plain">
              {{ statusLabel(row.online, row.healthy) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="数据频率" min-width="110">
        <template #default="{ row }">
          {{ formatNumber(row.measuredRateHz, 'Hz') }}
        </template>
      </el-table-column>

      <el-table-column label="延迟" min-width="100">
        <template #default="{ row }">
          {{ formatNumber(row.latencyMs, 'ms') }}
        </template>
      </el-table-column>

      <el-table-column label="TF状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="tfTagType(row.tfAvailable)" effect="plain">
            {{ tfLabel(row.tfAvailable) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="最后更新时间" min-width="180">
        <template #default="{ row }">
          {{ row.lastUpdateTime ?? '--' }}
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.vision-sensor-panel {
  margin-top: 20px;
  overflow: hidden;
}

.vision-sensor-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.vision-sensor-heading h2 {
  margin: 0;
  font-size: 18px;
}

.vision-sensor-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.vision-sensor-table {
  width: 100%;
}

@media (max-width: 768px) {
  .vision-sensor-heading {
    flex-direction: column;
  }
}
</style>