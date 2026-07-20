<script setup lang="ts">

import { getVisionDetections } from '@/services/visionDataService'
import type { VisionDetection } from '@/types/vision'

const detections = getVisionDetections()

function affiliationLabel(affiliation: VisionDetection['affiliation']) {
  const labels: Record<VisionDetection['affiliation'], string> = {
    FRIENDLY: '友方',
    HOSTILE: '敌方',
    NEUTRAL: '中立',
    UNKNOWN: '未知',
  }

  return labels[affiliation]
}

function affiliationTagType(affiliation: VisionDetection['affiliation']) {
  if (affiliation === 'FRIENDLY') return 'success'
  if (affiliation === 'HOSTILE') return 'danger'
  if (affiliation === 'NEUTRAL') return 'info'
  return 'warning'
}

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`
}

function formatPosition(x: number, y: number) {
  return `(${x.toFixed(1)}, ${y.toFixed(1)})`
}

function formatSpeed(x: number, y: number) {
  const speed = Math.sqrt(x * x + y * y)
  return `${speed.toFixed(1)} m/s`
}
</script>

<template>
  <section class="console-panel vision-detection-panel">
    <div class="vision-detection-heading">
      <div>
        <h2>视觉识别目标</h2>
        <p>展示相机、激光雷达及融合感知产生的目标信息。</p>
      </div>

      <div class="heading-actions">
        <el-tag type="primary" effect="plain">
          目标 {{ detections.length }}
        </el-tag>
        <el-tag effect="plain">静态预览</el-tag>
      </div>
    </div>

    <el-table :data="detections" class="vision-detection-table">
      <el-table-column prop="trackId" label="目标编号" min-width="120" />

      <el-table-column prop="className" label="目标类别" min-width="110" />

      <el-table-column label="敌我属性" min-width="100">
        <template #default="{ row }">
          <el-tag :type="affiliationTagType(row.affiliation)" effect="plain">
            {{ affiliationLabel(row.affiliation) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="sourceLabel" label="感知来源" min-width="150" />

      <el-table-column label="置信度" min-width="100">
        <template #default="{ row }">
          {{ formatConfidence(row.classConfidence) }}
        </template>
      </el-table-column>

      <el-table-column label="目标位置" min-width="140">
        <template #default="{ row }">
          {{ formatPosition(row.x, row.y) }}
        </template>
      </el-table-column>

      <el-table-column label="目标速度" min-width="110">
        <template #default="{ row }">
          {{ formatSpeed(row.speedX, row.speedY) }}
        </template>
      </el-table-column>

      <el-table-column prop="lastUpdateTime" label="最后更新时间" min-width="180" />
    </el-table>
  </section>
</template>

<style scoped>
.vision-detection-panel {
  margin-top: 20px;
  overflow: hidden;
}

.vision-detection-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.vision-detection-heading h2 {
  margin: 0;
  font-size: 18px;
}

.vision-detection-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.vision-detection-table {
  width: 100%;
}

@media (max-width: 768px) {
  .vision-detection-heading {
    flex-direction: column;
  }
}
</style>