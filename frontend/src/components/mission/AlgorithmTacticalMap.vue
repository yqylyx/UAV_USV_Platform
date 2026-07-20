<script setup lang="ts">
import { computed } from 'vue'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'
import { getAlgorithmMissionPreview } from '@/services/algorithmMissionDataService'
import { useAlgorithmStore } from '@/stores/algorithm'
import type { AlgorithmAssignmentItem, AlgorithmAssignmentRole } from '@/api/algorithm'
import type { AlgorithmVehicleType } from '@/types/algorithmMission'

const {
  currentCommandId,
  selectedMissionType,
  controlState,
  captureForm,
  escortForm,
} = useAlgorithmMissionDemo()
const algorithmStore = useAlgorithmStore()

const assignments = computed(() => algorithmStore.assignments)
const loading = computed(() => algorithmStore.loading)
const error = computed(() => algorithmStore.error)

const preview = computed(() =>
  getAlgorithmMissionPreview(selectedMissionType.value),
)

const mapCenterX = 300
const mapCenterY = 180
const coordinateScale = 2
const mapWidth = 600
const mapHeight = 360
const mapPadding = 48

const usesBackendMode = computed(() => !!currentCommandId.value)

const hasCurrentBackendAssignments = computed(() =>
  !!currentCommandId.value &&
  assignments.value?.commandId === currentCommandId.value,
)

const backendAssignments = computed(() =>
  hasCurrentBackendAssignments.value ? assignments.value?.assignments ?? [] : [],
)

const drawableBackendAssignments = computed(() =>
  backendAssignments.value.filter(
    (assignment) =>
      typeof assignment.x === 'number' &&
      Number.isFinite(assignment.x) &&
      typeof assignment.y === 'number' &&
      Number.isFinite(assignment.y),
  ),
)

const backendBounds = computed(() => {
  const xs = drawableBackendAssignments.value.map((assignment) => assignment.x as number)
  const ys = drawableBackendAssignments.value.map((assignment) => assignment.y as number)
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  }
})

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
  usesBackendMode.value
    ? '显示后端返回的任务分配坐标；目标中心坐标尚未由后端提供。'
    : selectedMissionType.value === 'CAPTURE'
      ? '演示预览围捕目标、围捕范围及异构平台分配位置。'
      : '演示预览被护航目标、护航范围、威胁方向及防守位置。',
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

function backendPointX(worldX: number) {
  const range = backendBounds.value.maxX - backendBounds.value.minX
  if (range === 0) return mapWidth / 2
  return mapPadding + ((worldX - backendBounds.value.minX) / range) * (mapWidth - mapPadding * 2)
}

function backendPointY(worldY: number) {
  const range = backendBounds.value.maxY - backendBounds.value.minY
  if (range === 0) return mapHeight / 2
  return mapHeight - mapPadding - ((worldY - backendBounds.value.minY) / range) * (mapHeight - mapPadding * 2)
}

function platformType(assignment: AlgorithmAssignmentItem): AlgorithmVehicleType | 'PLATFORM' {
  const candidates = [assignment.vehicleCode, assignment.vehicleId]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase().replace(/[-_]/g, ''))

  if (candidates.some((value) => value.startsWith('uav'))) return 'UAV'
  if (candidates.some((value) => value.startsWith('usv'))) return 'USV'
  return 'PLATFORM'
}

function vehicleColor(vehicleType: AlgorithmVehicleType | 'PLATFORM') {
  if (vehicleType === 'UAV') return '#56cfe1'
  if (vehicleType === 'USV') return '#ffd166'
  return '#cfd8dc'
}

function vehicleShortLabel(vehicleId: string) {
  return vehicleId.replace('uav_', 'U').replace('usv_', 'S')
}

function backendShortLabel(assignment: AlgorithmAssignmentItem) {
  const label = assignment.vehicleCode || assignment.vehicleId
  return label.replace(/^uav[-_]?/i, 'U').replace(/^usv[-_]?/i, 'S')
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

function formatBackendCoordinate(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '--'
}

function backendCoordinateLabel(assignment: AlgorithmAssignmentItem) {
  return `(${formatBackendCoordinate(assignment.x)}, ${formatBackendCoordinate(assignment.y)})`
}

function backendLabelX(worldX: number) {
  const point = backendPointX(worldX)
  return point > mapWidth - 150 ? point - 16 : point + 16
}

function backendLabelAnchor(worldX: number) {
  return backendPointX(worldX) > mapWidth - 150 ? 'end' : 'start'
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
          {{
            usesBackendMode
              ? loading
                ? '同步中'
                : drawableBackendAssignments.length > 0
                  ? '后端分配已加载'
                  : '等待后端分配'
              : controlStateLabel()
          }}
        </el-tag>

        <el-tag :type="usesBackendMode ? 'warning' : 'warning'" effect="plain">
          {{ usesBackendMode ? '后端返回分配' : '演示预览，非真实算法结果' }}
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="tactical-alert"
    />

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

          <template v-if="!usesBackendMode">
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

            <text
              x="300"
              y="30"
              text-anchor="middle"
              class="radius-label"
            >
              演示预览，非真实算法结果
            </text>
          </template>

          <template v-else>
            <text
              x="300"
              y="30"
              text-anchor="middle"
              class="radius-label"
            >
              目标中心坐标尚未由后端提供
            </text>

            <text
              v-if="drawableBackendAssignments.length === 0"
              x="300"
              y="180"
              text-anchor="middle"
              class="radius-label"
            >
              暂无后端任务分配坐标
            </text>

            <g
              v-for="assignment in drawableBackendAssignments"
              :key="`${assignment.vehicleId}-${assignment.role}`"
            >
              <circle
                :cx="backendPointX(assignment.x as number)"
                :cy="backendPointY(assignment.y as number)"
                r="12"
                :fill="vehicleColor(platformType(assignment))"
                stroke="#071f24"
                stroke-width="2"
              />

              <text
                :x="backendPointX(assignment.x as number)"
                :y="backendPointY(assignment.y as number) + 4"
                text-anchor="middle"
                class="vehicle-label"
              >
                {{ backendShortLabel(assignment) }}
              </text>

              <text
                :x="backendLabelX(assignment.x as number)"
                :y="backendPointY(assignment.y as number) - 10"
                :text-anchor="backendLabelAnchor(assignment.x as number)"
                class="radius-label"
              >
                <tspan>{{ assignment.vehicleCode || assignment.vehicleId }}</tspan>
                <tspan
                  :x="backendLabelX(assignment.x as number)"
                  dy="14"
                >
                  {{ assignmentRoleLabel(assignment.role) }}
                </tspan>
                <tspan
                  :x="backendLabelX(assignment.x as number)"
                  dy="14"
                >
                  {{ backendCoordinateLabel(assignment) }}
                </tspan>
              </text>
            </g>
          </template>
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
            <dd>{{ usesBackendMode ? '目标中心坐标尚未由后端提供' : preview.scene.centerLabel }}</dd>
          </div>

          <div>
            <dt>当前半径</dt>
            <dd>{{ activeRadius }} m</dd>
          </div>

          <div>
            <dt>分配平台</dt>
            <dd>{{ usesBackendMode ? drawableBackendAssignments.length : preview.assignments.length }} 个</dd>
          </div>

          <div v-if="!usesBackendMode && preview.scene.threatLabel">
            <dt>威胁目标</dt>
            <dd>{{ preview.scene.threatLabel }}</dd>
          </div>

          <div v-if="usesBackendMode && selectedMissionType === 'ESCORT_DEFENSE'">
            <dt>威胁目标</dt>
            <dd>威胁目标坐标尚未由后端提供</dd>
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

          <span v-if="!usesBackendMode">
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

          <span v-if="!usesBackendMode && selectedMissionType === 'ESCORT_DEFENSE'">
            <i class="legend-dot threat" />
            威胁目标
          </span>
        </div>

        <el-alert
          :title="usesBackendMode ? '后端返回分配' : '演示预览，非真实算法结果'"
          :description="
            usesBackendMode
              ? '图中位置来自后端返回的任务分配；当前后端可能使用模拟分配，尚不能代表Python真实算法结果。目标中心和威胁坐标尚未由后端提供。'
              : '图中位置来自演示数据，尚未接收Python算法或Unity实时坐标。'
          "
          :type="usesBackendMode ? 'warning' : 'warning'"
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

.tactical-alert {
  margin-bottom: 18px;
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
