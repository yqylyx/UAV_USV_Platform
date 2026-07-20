<script setup lang="ts">
import { computed } from 'vue'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'
import { getAlgorithmMissionPreview } from '@/services/algorithmMissionDataService'
import type { AlgorithmVehicleType } from '@/types/algorithmMission'

const {
  selectedMissionType,
  controlState,
  captureForm,
  escortForm,
} = useAlgorithmMissionDemo()

const preview = computed(() =>
  getAlgorithmMissionPreview(selectedMissionType.value),
)

const mapCenterX = 300
const mapCenterY = 180
const coordinateScale = 2

const activeRadius = computed(() =>
  selectedMissionType.value === 'CAPTURE'
    ? captureForm.captureRadius
    : escortForm.escortRadius,
)

const ringRadius = computed(() =>
  Math.min(Math.max(activeRadius.value * coordinateScale, 35), 145),
)

const mapTitle = computed(() =>
  selectedMissionType.value === 'CAPTURE'
    ? '围捕战术态势'
    : '护航防守态势',
)

const mapDescription = computed(() =>
  selectedMissionType.value === 'CAPTURE'
    ? '展示围捕目标、围捕范围及异构平台分配位置。'
    : '展示被护航目标、护航范围、威胁方向及防守位置。',
)

function pointX(worldX: number) {
  return (
    mapCenterX +
    (worldX - preview.value.scene.centerX) * coordinateScale
  )
}

function pointY(worldY: number) {
  return (
    mapCenterY -
    (worldY - preview.value.scene.centerY) * coordinateScale
  )
}

function vehicleColor(vehicleType: AlgorithmVehicleType) {
  return vehicleType === 'UAV' ? '#56cfe1' : '#ffd166'
}

function vehicleShortLabel(vehicleId: string) {
  return vehicleId.replace('uav_', 'U').replace('usv_', 'S')
}

function controlStateLabel() {
  if (controlState.value === 'RUNNING') return '演示运行中'
  if (controlState.value === 'STOPPED') return '演示已停止'
  return '等待启动'
}

function controlStateTagType() {
  if (controlState.value === 'RUNNING') return 'success'
  if (controlState.value === 'STOPPED') return 'danger'
  return 'info'
}
</script>

<template>
  <section class="console-panel algorithm-tactical-map">
    <div class="tactical-heading">
      <div>
        <h2>{{ mapTitle }}</h2>
        <p>{{ mapDescription }}</p>
      </div>

      <div class="tactical-heading-actions">
        <el-tag :type="controlStateTagType()" effect="plain">
          {{ controlStateLabel() }}
        </el-tag>

        <el-tag type="warning" effect="plain">
          战术预览
        </el-tag>
      </div>
    </div>

    <div class="tactical-layout">
      <div class="map-container">
        <svg
          viewBox="0 0 600 360"
          role="img"
          :aria-label="mapTitle"
          class="tactical-svg"
        >
          <defs>
            <pattern
              id="algorithm-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(86, 207, 225, 0.10)"
                stroke-width="1"
              />
            </pattern>

            <marker
              id="threat-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path
                d="M0,0 L8,4 L0,8 Z"
                fill="#ff6b6b"
              />
            </marker>
          </defs>

          <rect
            x="0"
            y="0"
            width="600"
            height="360"
            fill="url(#algorithm-grid)"
          />

          <circle
            :cx="mapCenterX"
            :cy="mapCenterY"
            :r="ringRadius"
            fill="rgba(86, 207, 225, 0.06)"
            stroke="#56cfe1"
            stroke-width="2"
            stroke-dasharray="8 6"
          />

          <circle
            v-if="selectedMissionType === 'ESCORT_DEFENSE'"
            :cx="mapCenterX"
            :cy="mapCenterY"
            :r="Math.min(ringRadius + escortForm.defenseDistance, 165)"
            fill="none"
            stroke="rgba(255, 209, 102, 0.65)"
            stroke-width="1.5"
            stroke-dasharray="4 7"
          />

          <g
            v-for="assignment in preview.assignments"
            :key="assignment.vehicleId"
          >
            <line
              :x1="mapCenterX"
              :y1="mapCenterY"
              :x2="pointX(assignment.targetX)"
              :y2="pointY(assignment.targetY)"
              :stroke="vehicleColor(assignment.vehicleType)"
              stroke-width="1.5"
              stroke-dasharray="5 5"
              opacity="0.65"
            />

            <circle
              :cx="pointX(assignment.targetX)"
              :cy="pointY(assignment.targetY)"
              r="12"
              :fill="vehicleColor(assignment.vehicleType)"
              stroke="#071f24"
              stroke-width="2"
            />

            <text
              :x="pointX(assignment.targetX)"
              :y="pointY(assignment.targetY) + 4"
              text-anchor="middle"
              class="vehicle-label"
            >
              {{ vehicleShortLabel(assignment.vehicleId) }}
            </text>
          </g>

          <line
            v-if="
              preview.scene.threatX !== null &&
              preview.scene.threatY !== null
            "
            :x1="pointX(preview.scene.threatX)"
            :y1="pointY(preview.scene.threatY)"
            :x2="mapCenterX + 18"
            :y2="mapCenterY - 8"
            stroke="#ff6b6b"
            stroke-width="3"
            stroke-dasharray="10 6"
            marker-end="url(#threat-arrow)"
          />

          <g
            v-if="
              preview.scene.threatX !== null &&
              preview.scene.threatY !== null
            "
          >
            <circle
              :cx="pointX(preview.scene.threatX)"
              :cy="pointY(preview.scene.threatY)"
              r="15"
              fill="#ff6b6b"
              stroke="#ffd1d1"
              stroke-width="2"
            />

            <text
              :x="pointX(preview.scene.threatX)"
              :y="pointY(preview.scene.threatY) + 4"
              text-anchor="middle"
              class="threat-label"
            >
              E
            </text>
          </g>

          <circle
            :cx="mapCenterX"
            :cy="mapCenterY"
            r="18"
            :fill="
              selectedMissionType === 'CAPTURE'
                ? '#ff6b6b'
                : '#80ed99'
            "
            stroke="#ffffff"
            stroke-width="2"
          />

          <text
            :x="mapCenterX"
            :y="mapCenterY + 5"
            text-anchor="middle"
            class="center-label"
          >
            {{ selectedMissionType === 'CAPTURE' ? 'T' : 'P' }}
          </text>

          <text
            :x="mapCenterX"
            :y="mapCenterY + ringRadius + 24"
            text-anchor="middle"
            class="radius-label"
          >
            {{
              selectedMissionType === 'CAPTURE'
                ? `围捕半径 ${captureForm.captureRadius} m`
                : `护航半径 ${escortForm.escortRadius} m`
            }}
          </text>
        </svg>
      </div>

      <aside class="tactical-information">
        <h3>态势说明</h3>

        <dl>
          <div>
            <dt>当前模式</dt>
            <dd>
              {{
                selectedMissionType === 'CAPTURE'
                  ? '协同围捕'
                  : '护航防守'
              }}
            </dd>
          </div>

          <div>
            <dt>中心目标</dt>
            <dd>{{ preview.scene.centerLabel }}</dd>
          </div>

          <div>
            <dt>当前半径</dt>
            <dd>{{ activeRadius }} m</dd>
          </div>

          <div>
            <dt>分配平台</dt>
            <dd>{{ preview.assignments.length }} 个</dd>
          </div>

          <div v-if="preview.scene.threatLabel">
            <dt>威胁目标</dt>
            <dd>{{ preview.scene.threatLabel }}</dd>
          </div>

          <div v-if="selectedMissionType === 'ESCORT_DEFENSE'">
            <dt>防守距离</dt>
            <dd>{{ escortForm.defenseDistance }} m</dd>
          </div>
        </dl>

        <div class="tactical-legend">
          <h4>图例</h4>

          <span>
            <i class="legend-dot uav" />
            UAV分配点
          </span>

          <span>
            <i class="legend-dot usv" />
            USV分配点
          </span>

          <span>
            <i
              class="legend-dot"
              :class="
                selectedMissionType === 'CAPTURE'
                  ? 'target'
                  : 'protected'
              "
            />
            {{
              selectedMissionType === 'CAPTURE'
                ? '围捕目标'
                : '被护航目标'
            }}
          </span>

          <span v-if="selectedMissionType === 'ESCORT_DEFENSE'">
            <i class="legend-dot threat" />
            威胁目标
          </span>
        </div>

        <el-alert
          title="前端战术预览"
          description="图中位置来自演示数据，尚未接收Python算法或Unity实时坐标。"
          type="warning"
          show-icon
          :closable="false"
        />
      </aside>
    </div>
  </section>
</template>

<style scoped>
.algorithm-tactical-map {
  margin-bottom: 20px;
  overflow: hidden;
}

.tactical-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.tactical-heading h2 {
  margin: 0;
  font-size: 18px;
}

.tactical-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.tactical-heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tactical-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(280px, 0.7fr);
  gap: 18px;
}

.map-container {
  min-height: 400px;
  padding: 16px;
  border: 1px solid rgba(86, 207, 225, 0.3);
  border-radius: 10px;
  background: rgba(4, 20, 25, 0.72);
}

.tactical-svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 360px;
}

.vehicle-label,
.center-label,
.threat-label {
  fill: #071f24;
  font-size: 10px;
  font-weight: 700;
  pointer-events: none;
}

.center-label,
.threat-label {
  font-size: 12px;
}

.radius-label {
  fill: rgba(216, 245, 247, 0.75);
  font-size: 12px;
}

.tactical-information {
  padding: 18px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 10px;
  background: rgba(8, 35, 40, 0.45);
}

.tactical-information h3,
.tactical-information h4 {
  margin: 0;
}

.tactical-information h3 {
  margin-bottom: 16px;
  font-size: 16px;
}

.tactical-information dl {
  display: grid;
  gap: 12px;
  margin: 0 0 18px;
}

.tactical-information dt {
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.tactical-information dd {
  margin: 0;
  font-size: 14px;
}

.tactical-legend {
  display: grid;
  gap: 10px;
  margin-bottom: 18px;
  padding: 14px;
  border: 1px solid rgba(86, 207, 225, 0.16);
  border-radius: 8px;
}

.tactical-legend h4 {
  margin-bottom: 2px;
  font-size: 14px;
}

.tactical-legend span {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.legend-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
}

.legend-dot.uav {
  background: #56cfe1;
}

.legend-dot.usv {
  background: #ffd166;
}

.legend-dot.target,
.legend-dot.threat {
  background: #ff6b6b;
}

.legend-dot.protected {
  background: #80ed99;
}

@media (max-width: 1000px) {
  .tactical-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .tactical-heading {
    flex-direction: column;
  }

  .map-container {
    min-height: 300px;
    padding: 6px;
  }

  .tactical-svg {
    min-height: 280px;
  }
}
</style>