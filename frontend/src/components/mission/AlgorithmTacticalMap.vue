<script setup lang="ts">
import { computed } from 'vue'

import {
  isCompletePosition,
  useAlgorithmMissionDemo,
} from '@/composables/useAlgorithmMissionDemo'
import { useAlgorithmStore } from '@/stores/algorithm'
import type { AlgorithmAssignmentItem, AlgorithmAssignmentRole } from '@/api/algorithm'
import type { AlgorithmMissionType } from '@/types/algorithmMission'

type AlgorithmVehicleType = 'UAV' | 'USV'

interface TacticalPoint {
  id: string
  label: string
  vehicleType: AlgorithmVehicleType | 'PLATFORM'
  x: number
  y: number
}

interface TacticalTargetPoint {
  id: string
  label: string
  description: string
  x: number
  y: number
  kind: 'target' | 'threat'
}

const {
  currentCommandId,
  selectedMissionType,
  controlState,
  positionSource,
  manualVehiclePositions,
  submittedPositionSource,
  submittedTargetId,
  submittedTargetPosition,
  submittedThreatTargetId,
  submittedThreatPosition,
  captureForm,
  escortForm,
} = useAlgorithmMissionDemo()
const algorithmStore = useAlgorithmStore()

const assignments = computed(() => algorithmStore.assignments)
const loading = computed(() => algorithmStore.loading)
const error = computed(() => algorithmStore.error)

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

const activeRadius = computed(() =>
  selectedMissionType.value === 'CAPTURE'
    ? captureForm.captureRadius
    : escortForm.escortRadius,
)

const mapTitle = computed(() =>
  selectedMissionType.value === 'CAPTURE'
    ? '围捕战术态势'
    : '护航防守态势',
)

const resultPositionSource = computed(() =>
  submittedPositionSource.value ?? 'REALTIME',
)

const positionSourceLabel = computed(() =>
  usesBackendMode.value
    ? resultPositionSource.value === 'MANUAL'
      ? '车辆初始位姿来自人工输入'
      : '车辆初始位姿来自实时运行状态'
    : positionSource.value === 'MANUAL'
      ? '手动初始位姿输入预览，非算法分配结果'
      : '尚未获得算法分配，启动后将显示真实Python结果',
)

const mapDescription = computed(() =>
  usesBackendMode.value
    ? submittedThreatPosition.value
      ? '车辆分配位置来自真实Python算法返回；护航目标和威胁目标来自本次任务输入。'
      : '车辆分配位置来自真实Python算法返回；任务目标来自本次任务输入。'
    : positionSource.value === 'MANUAL'
      ? '手动初始位姿输入预览，非算法分配结果。'
      : '尚未获得算法分配，启动后将显示真实Python结果。',
)

const targetLegendLabel = computed(() =>
  usesBackendMode.value
    ? submittedThreatPosition.value
      ? '用户输入护航目标'
      : '用户输入围捕目标'
    : '用户输入目标',
)

const selectedVehicleKeySet = computed(() => {
  const form = selectedMissionType.value === 'CAPTURE' ? captureForm : escortForm
  return new Set([...form.uavIds, ...form.usvIds])
})

const manualPreviewPoints = computed<TacticalPoint[]>(() =>
  manualVehiclePositions
    .filter((item) => selectedVehicleKeySet.value.has(item.vehicleId))
    .flatMap((item) => {
      const position = item.position
      if (!isCompletePosition(position)) return []

      return [{
        id: item.vehicleId,
        label: vehicleShortLabel(item.vehicleId),
        vehicleType: vehicleTypeFromId(item.vehicleId),
        x: position.x,
        y: position.y,
      }]
    }),
)

const inputTargetPoints = computed<TacticalTargetPoint[]>(() => {
  if (usesBackendMode.value || positionSource.value !== 'MANUAL') return []

  const points: TacticalTargetPoint[] = []
  if (selectedMissionType.value === 'CAPTURE') {
    if (isCompletePosition(captureForm.targetPosition)) {
      points.push({
        id: 'target',
        label: '用户输入目标',
        description: '围捕目标（任务输入）',
        x: captureForm.targetPosition.x,
        y: captureForm.targetPosition.y,
        kind: 'target',
      })
    }
    return points
  }

  if (isCompletePosition(escortForm.targetPosition)) {
    points.push({
      id: 'escort-target',
      label: '用户输入目标',
      description: '护航目标（任务输入）',
      x: escortForm.targetPosition.x,
      y: escortForm.targetPosition.y,
      kind: 'target',
    })
  }
  if (isCompletePosition(escortForm.threatPosition)) {
    points.push({
      id: 'threat',
      label: '用户输入威胁',
      description: '威胁目标（任务输入）',
      x: escortForm.threatPosition.x,
      y: escortForm.threatPosition.y,
      kind: 'threat',
    })
  }
  return points
})

const submittedTargetPoints = computed<TacticalTargetPoint[]>(() => {
  if (!usesBackendMode.value || !submittedTargetPosition.value) return []

  const points: TacticalTargetPoint[] = [{
    id: submittedTargetId.value || 'target',
    label: submittedTargetId.value || '任务目标',
    description: submittedThreatPosition.value ? '护航目标（任务输入）' : '围捕目标（任务输入）',
    x: submittedTargetPosition.value.x,
    y: submittedTargetPosition.value.y,
    kind: 'target',
  }]

  if (submittedThreatPosition.value) {
    points.push({
      id: submittedThreatTargetId.value || 'threat',
      label: submittedThreatTargetId.value || '威胁目标',
      description: '威胁目标（任务输入）',
      x: submittedThreatPosition.value.x,
      y: submittedThreatPosition.value.y,
      kind: 'threat',
    })
  }

  return points
})

const visibleTargetPoints = computed(() =>
  usesBackendMode.value ? submittedTargetPoints.value : inputTargetPoints.value,
)

const plottedPoints = computed(() =>
  usesBackendMode.value
    ? drawableBackendAssignments.value.map((assignment) => ({
        id: `${assignment.vehicleId}-${assignment.role}`,
        label: backendShortLabel(assignment),
        vehicleType: platformType(assignment),
        x: assignment.x as number,
        y: assignment.y as number,
      }))
    : manualPreviewPoints.value,
)

const bounds = computed(() => {
  const allPoints = [
    ...plottedPoints.value,
    ...visibleTargetPoints.value.map((point) => ({
      id: point.id,
      label: point.label,
      vehicleType: 'PLATFORM' as const,
      x: point.x,
      y: point.y,
    })),
  ]

  if (allPoints.length === 0) {
    return { minX: 0, maxX: 0, minY: 0, maxY: 0 }
  }

  const xs = allPoints.map((point) => point.x)
  const ys = allPoints.map((point) => point.y)
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  }
})

function mapPointX(worldX: number) {
  const range = bounds.value.maxX - bounds.value.minX
  if (range === 0) return mapWidth / 2
  return mapPadding + ((worldX - bounds.value.minX) / range) * (mapWidth - mapPadding * 2)
}

function mapPointY(worldY: number) {
  const range = bounds.value.maxY - bounds.value.minY
  if (range === 0) return mapHeight / 2
  return mapHeight - mapPadding - ((worldY - bounds.value.minY) / range) * (mapHeight - mapPadding * 2)
}

function platformType(assignment: AlgorithmAssignmentItem): AlgorithmVehicleType | 'PLATFORM' {
  return vehicleTypeFromId(`${assignment.vehicleCode ?? ''} ${assignment.vehicleId}`)
}

function vehicleTypeFromId(vehicleId: string): AlgorithmVehicleType | 'PLATFORM' {
  const normalized = vehicleId.toLowerCase().replace(/[-_]/g, '')

  if (normalized.includes('uav')) return 'UAV'
  if (normalized.includes('usv')) return 'USV'
  return 'PLATFORM'
}

function vehicleColor(vehicleType: AlgorithmVehicleType | 'PLATFORM') {
  if (vehicleType === 'UAV') return '#56cfe1'
  if (vehicleType === 'USV') return '#ffd166'
  return '#cfd8dc'
}

function vehicleShortLabel(vehicleId: string) {
  return vehicleId.replace(/^uav[-_]?/i, 'U').replace(/^usv[-_]?/i, 'S')
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

function coordinateLabel(point: { x: number; y: number }) {
  return `(${formatBackendCoordinate(point.x)}, ${formatBackendCoordinate(point.y)})`
}

function labelX(worldX: number) {
  const point = mapPointX(worldX)
  return point > mapWidth - 150 ? point - 16 : point + 16
}

function labelAnchor(worldX: number) {
  return mapPointX(worldX) > mapWidth - 150 ? 'end' : 'start'
}

function targetLabelX(point: TacticalTargetPoint) {
  const base = mapPointX(point.x)
  return point.kind === 'threat'
    ? Math.min(base + 28, mapWidth - mapPadding)
    : labelX(point.x)
}

function targetLabelY(point: TacticalTargetPoint) {
  const base = mapPointY(point.y)
  return point.kind === 'threat' ? Math.max(base - 30, mapPadding) : base - 18
}

function targetLabelAnchor(point: TacticalTargetPoint) {
  if (point.kind === 'threat') return 'start'
  return labelAnchor(point.x)
}

function controlStateLabel() {
  if (controlState.value === 'RUNNING') return '算法已提交'
  if (controlState.value === 'STOPPED') return '算法已停止'
  return '等待启动'
}

function controlStateTagType() {
  if (controlState.value === 'RUNNING') return 'success'
  if (controlState.value === 'STOPPED') return 'danger'
  return 'info'
}

function missionTypeLabel(type: AlgorithmMissionType) {
  return type === 'CAPTURE' ? '协同围捕' : '护航防守'
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
                  ? '真实结果已加载'
                  : '等待真实结果'
              : controlStateLabel()
          }}
        </el-tag>

        <el-tag effect="plain">
          {{ usesBackendMode ? '真实Python算法结果' : positionSourceLabel }}
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
          </defs>

          <rect
            x="0"
            y="0"
            width="600"
            height="360"
            fill="url(#algorithm-grid)"
          />

          <template v-if="usesBackendMode">
            <text
              x="300"
              y="30"
              text-anchor="middle"
              class="radius-label"
            >
              {{ mapDescription }}
            </text>

            <text
              x="300"
              y="48"
              text-anchor="middle"
              class="radius-label"
            >
              {{ positionSourceLabel }}
            </text>

            <text
              v-if="drawableBackendAssignments.length === 0"
              x="300"
              y="180"
              text-anchor="middle"
              class="radius-label"
            >
              尚未获得算法分配，启动后将显示真实Python结果。
            </text>

            <g
              v-for="assignment in drawableBackendAssignments"
              :key="`${assignment.vehicleId}-${assignment.role}`"
            >
              <circle
                :cx="mapPointX(assignment.x as number)"
                :cy="mapPointY(assignment.y as number)"
                r="12"
                :fill="vehicleColor(platformType(assignment))"
                stroke="#071f24"
                stroke-width="2"
              />

              <text
                :x="mapPointX(assignment.x as number)"
                :y="mapPointY(assignment.y as number) + 4"
                text-anchor="middle"
                class="vehicle-label"
              >
                {{ backendShortLabel(assignment) }}
              </text>

              <text
                :x="labelX(assignment.x as number)"
                :y="mapPointY(assignment.y as number) - 10"
                :text-anchor="labelAnchor(assignment.x as number)"
                class="radius-label"
              >
                <tspan>{{ assignment.vehicleCode || assignment.vehicleId }}</tspan>
                <tspan
                  :x="labelX(assignment.x as number)"
                  dy="14"
                >
                  {{ assignmentRoleLabel(assignment.role) }}
                </tspan>
                <tspan
                  :x="labelX(assignment.x as number)"
                  dy="14"
                >
                  {{ coordinateLabel({ x: assignment.x as number, y: assignment.y as number }) }}
                </tspan>
              </text>
            </g>

            <g
              v-for="target in submittedTargetPoints"
              :key="`submitted-${target.kind}-${target.id}`"
            >
              <polygon
                v-if="target.kind === 'threat'"
                :points="`
                  ${mapPointX(target.x)},${mapPointY(target.y) - 19}
                  ${mapPointX(target.x) + 19},${mapPointY(target.y)}
                  ${mapPointX(target.x)},${mapPointY(target.y) + 19}
                  ${mapPointX(target.x) - 19},${mapPointY(target.y)}
                `"
                fill="#ff6b6b"
                stroke="#ffe1d6"
                stroke-width="3"
              />

              <circle
                v-else
                :cx="mapPointX(target.x)"
                :cy="mapPointY(target.y)"
                r="17"
                fill="#80ed99"
                stroke="#ffffff"
                stroke-width="3"
              />

              <text
                :x="mapPointX(target.x)"
                :y="mapPointY(target.y) + 5"
                text-anchor="middle"
                class="center-label"
              >
                {{ target.kind === 'threat' ? '!' : 'T' }}
              </text>

              <text
                :x="targetLabelX(target)"
                :y="targetLabelY(target)"
                :text-anchor="targetLabelAnchor(target)"
                class="radius-label"
              >
                <tspan>{{ target.label }}</tspan>
                <tspan
                  :x="targetLabelX(target)"
                  dy="14"
                >
                  {{ target.description }}
                </tspan>
                <tspan
                  :x="targetLabelX(target)"
                  dy="14"
                >
                  {{ coordinateLabel(target) }}
                </tspan>
              </text>
            </g>
          </template>

          <template v-else-if="positionSource === 'MANUAL'">
            <text
              x="300"
              y="30"
              text-anchor="middle"
              class="radius-label"
            >
              手动初始位姿输入预览，非算法分配结果
            </text>

            <text
              v-if="manualPreviewPoints.length === 0"
              x="300"
              y="180"
              text-anchor="middle"
              class="radius-label"
            >
              请完整填写车辆初始位姿后预览输入位置
            </text>

            <g
              v-for="target in inputTargetPoints"
              :key="target.id"
            >
              <circle
                :cx="mapPointX(target.x)"
                :cy="mapPointY(target.y)"
                r="15"
                :fill="target.kind === 'threat' ? '#ff6b6b' : '#80ed99'"
                stroke="#ffffff"
                stroke-width="2"
              />

              <text
                :x="mapPointX(target.x)"
                :y="mapPointY(target.y) + 4"
                text-anchor="middle"
                class="center-label"
              >
                {{ target.kind === 'threat' ? 'E' : 'T' }}
              </text>

              <text
                :x="labelX(target.x)"
                :y="mapPointY(target.y) - 12"
                :text-anchor="labelAnchor(target.x)"
                class="radius-label"
              >
                {{ target.label }}
              </text>
            </g>

            <g
              v-for="point in manualPreviewPoints"
              :key="point.id"
            >
              <circle
                :cx="mapPointX(point.x)"
                :cy="mapPointY(point.y)"
                r="12"
                :fill="vehicleColor(point.vehicleType)"
                stroke="#071f24"
                stroke-width="2"
              />

              <text
                :x="mapPointX(point.x)"
                :y="mapPointY(point.y) + 4"
                text-anchor="middle"
                class="vehicle-label"
              >
                {{ point.label }}
              </text>

              <text
                :x="labelX(point.x)"
                :y="mapPointY(point.y) - 10"
                :text-anchor="labelAnchor(point.x)"
                class="radius-label"
              >
                <tspan>{{ point.id }}</tspan>
                <tspan
                  :x="labelX(point.x)"
                  dy="14"
                >
                  手动输入
                </tspan>
                <tspan
                  :x="labelX(point.x)"
                  dy="14"
                >
                  {{ coordinateLabel(point) }}
                </tspan>
              </text>
            </g>
          </template>

          <template v-else>
            <text
              x="300"
              y="180"
              text-anchor="middle"
              class="radius-label"
            >
              尚未获得算法分配，启动后将显示真实Python结果。
            </text>
          </template>
        </svg>
      </div>

      <aside class="tactical-information">
        <h3>态势说明</h3>

        <dl>
          <div>
            <dt>当前模式</dt>
            <dd>{{ missionTypeLabel(selectedMissionType) }}</dd>
          </div>

          <div>
            <dt>数据来源</dt>
            <dd>{{ usesBackendMode ? '真实Python算法结果' : positionSourceLabel }}</dd>
          </div>

          <div>
            <dt>当前半径</dt>
            <dd>{{ activeRadius }} m</dd>
          </div>

          <div>
            <dt>{{ usesBackendMode ? '分配平台' : '预览平台' }}</dt>
            <dd>{{ usesBackendMode ? drawableBackendAssignments.length : manualPreviewPoints.length }} 个</dd>
          </div>

          <div v-if="!usesBackendMode && inputTargetPoints.length > 0">
            <dt>用户输入目标</dt>
            <dd>{{ inputTargetPoints.map((point) => point.label).join(' / ') }}</dd>
          </div>

          <div v-if="usesBackendMode && submittedTargetPoints.length > 0">
            <dt>任务输入目标</dt>
            <dd>{{ submittedTargetPoints.map((point) => point.label).join(' / ') }}</dd>
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
            UAV{{ usesBackendMode ? '算法分配点' : '输入点' }}
          </span>

          <span>
            <i class="legend-dot usv" />
            USV{{ usesBackendMode ? '算法分配点' : '输入点' }}
          </span>

          <span v-if="submittedTargetPoints.some((point) => point.kind === 'target') || (!usesBackendMode && positionSource === 'MANUAL')">
            <i class="legend-dot protected" />
            {{ targetLegendLabel }}
          </span>

          <span v-if="submittedTargetPoints.some((point) => point.kind === 'threat') || (!usesBackendMode && positionSource === 'MANUAL' && selectedMissionType === 'ESCORT_DEFENSE')">
            <i class="legend-dot threat" />
            用户输入威胁
          </span>
        </div>

        <el-alert
          :title="usesBackendMode ? '真实Python算法结果' : positionSourceLabel"
          :description="
            usesBackendMode
              ? `${mapDescription} 目标点为任务请求输入，不计入分配平台数量。`
              : positionSource === 'MANUAL'
                ? '手动初始位姿输入预览，非算法分配结果；启动成功后只显示真实Python返回的assignment。'
                : '尚未获得算法分配，启动后将显示真实Python结果。'
          "
          :type="usesBackendMode ? 'success' : positionSource === 'MANUAL' ? 'warning' : 'info'"
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
