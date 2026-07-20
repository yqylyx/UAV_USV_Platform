<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'

import {
  isCompletePosition,
  toAlgorithmPosition,
  useAlgorithmMissionDemo,
} from '@/composables/useAlgorithmMissionDemo'
import type {
  AlgorithmStartPayload,
  AlgorithmVehiclePosition,
} from '@/api/algorithm'
import { useAlgorithmStore } from '@/stores/algorithm'

const {
  selectedMissionType,
  controlState,
  currentCommandId,
  positionSource,
  manualVehiclePositions,
  captureForm,
  escortForm,
  getManualVehiclePosition,
  startDemo,
  stopDemo,
  resetDemo,
} = useAlgorithmMissionDemo()

const algorithmStore = useAlgorithmStore()
const starting = ref(false)
const stopping = ref(false)

const uavOptions = [
  { label: 'UAV-01', value: 'uav_01' },
  { label: 'UAV-02', value: 'uav_02' },
  { label: 'UAV-03', value: 'uav_03' },
]

const usvOptions = [
  { label: 'USV-01', value: 'usv_01' },
  { label: 'USV-02', value: 'usv_02' },
  { label: 'USV-03', value: 'usv_03' },
]

const threatDirectionOptions = [
  { label: '正前方', value: 'FRONT' },
  { label: '右前方', value: 'FRONT_RIGHT' },
  { label: '正右方', value: 'RIGHT' },
  { label: '右后方', value: 'BACK_RIGHT' },
  { label: '正后方', value: 'BACK' },
  { label: '左后方', value: 'BACK_LEFT' },
  { label: '正左方', value: 'LEFT' },
  { label: '左前方', value: 'FRONT_LEFT' },
]

const sourceOptions = [
  { label: '实时位姿', value: 'REALTIME' },
  { label: '手动初始位姿实验', value: 'MANUAL' },
] as const

const activeUavIds = computed(() =>
  selectedMissionType.value === 'CAPTURE' ? captureForm.uavIds : escortForm.uavIds,
)

const activeUsvIds = computed(() =>
  selectedMissionType.value === 'CAPTURE' ? captureForm.usvIds : escortForm.usvIds,
)

const selectedVehicleIds = computed(() => [...activeUavIds.value, ...activeUsvIds.value])

const manualUavRows = computed(() =>
  activeUavIds.value.map((vehicleId) => getManualVehiclePosition(vehicleId)),
)

const manualUsvRows = computed(() =>
  activeUsvIds.value.map((vehicleId) => getManualVehiclePosition(vehicleId)),
)

function normalizeVehicleId(vehicleId: string) {
  return vehicleId.trim().toLowerCase().replace(/_/g, '-')
}

function vehicleLabel(vehicleId: string) {
  return [...uavOptions, ...usvOptions].find((option) => option.value === vehicleId)?.label ?? vehicleId
}

function hasMissingCoordinate(position: {
  x: number | null
  y: number | null
  z: number | null
  heading: number | null
}) {
  return (
    position.x === null ||
    position.y === null ||
    position.z === null ||
    position.heading === null
  )
}

function controlStateLabel() {
  if (controlState.value === 'RUNNING') return '算法已提交'
  if (controlState.value === 'STOPPED') return '已提交停止'
  return '等待启动'
}

function controlStateTagType() {
  if (controlState.value === 'RUNNING') return 'success'
  if (controlState.value === 'STOPPED') return 'danger'
  return 'info'
}

function validateCaptureForm() {
  if (!captureForm.targetId.trim()) {
    ElMessage.warning('请选择或填写围捕目标')
    return false
  }

  if (!toAlgorithmPosition(captureForm.targetPosition)) {
    ElMessage.warning('请完整填写围捕目标坐标')
    return false
  }

  const totalAgents = captureForm.uavIds.length + captureForm.usvIds.length

  if (totalAgents === 0) {
    ElMessage.warning('请至少选择一个参与平台')
    return false
  }

  if (captureForm.minimumAgents > totalAgents) {
    ElMessage.warning('最少围捕平台数不能超过已选择的平台总数')
    return false
  }

  return true
}

function validateEscortForm() {
  if (!escortForm.escortTargetId.trim()) {
    ElMessage.warning('请填写被护航目标')
    return false
  }

  if (!escortForm.threatTargetId.trim()) {
    ElMessage.warning('请填写威胁目标')
    return false
  }

  if (!toAlgorithmPosition(escortForm.targetPosition) || !toAlgorithmPosition(escortForm.threatPosition)) {
    ElMessage.warning('请完整填写护航目标和威胁目标坐标')
    return false
  }

  if (escortForm.uavIds.length === 0 && escortForm.usvIds.length === 0) {
    ElMessage.warning('请至少选择一个参与平台')
    return false
  }

  return true
}

function buildManualVehiclePositions(): AlgorithmVehiclePosition[] | null {
  if (positionSource.value !== 'MANUAL') return []

  const selectedKeys = new Map<string, string>()
  for (const vehicleId of selectedVehicleIds.value) {
    const key = normalizeVehicleId(vehicleId)
    if (selectedKeys.has(key)) {
      ElMessage.warning(`${vehicleLabel(vehicleId)} 的手动初始位姿重复`)
      return null
    }
    selectedKeys.set(key, vehicleId)
  }

  const rowsByKey = new Map<string, (typeof manualVehiclePositions)[number]>()
  for (const row of manualVehiclePositions) {
    const key = normalizeVehicleId(row.vehicleId)
    if (rowsByKey.has(key)) {
      ElMessage.warning(`${vehicleLabel(row.vehicleId)} 的手动初始位姿重复`)
      return null
    }
    if (!selectedKeys.has(key)) {
      ElMessage.warning(`${vehicleLabel(row.vehicleId)} 不是当前选择车辆`)
      return null
    }
    rowsByKey.set(key, row)
  }

  const payload: AlgorithmVehiclePosition[] = []
  for (const vehicleId of selectedVehicleIds.value) {
    const row = rowsByKey.get(normalizeVehicleId(vehicleId))
    if (!row || hasMissingCoordinate(row.position)) {
      ElMessage.warning(`请完整填写 ${vehicleLabel(vehicleId)} 的手动初始位姿`)
      return null
    }

    if (!isCompletePosition(row.position)) {
      ElMessage.warning(`${vehicleLabel(vehicleId)} 的初始位姿必须是有限数字`)
      return null
    }

    payload.push({
      vehicleId,
      position: {
        x: row.position.x,
        y: row.position.y,
        z: row.position.z,
        heading: row.position.heading,
      },
    })
  }

  return payload
}

async function handleStart() {
  const valid =
    selectedMissionType.value === 'CAPTURE'
      ? validateCaptureForm()
      : validateEscortForm()

  if (!valid) return

  const captureTargetPosition = toAlgorithmPosition(captureForm.targetPosition)
  const escortTargetPosition = toAlgorithmPosition(escortForm.targetPosition)
  const escortThreatPosition = toAlgorithmPosition(escortForm.threatPosition)
  const manualPositions = buildManualVehiclePositions()

  if (manualPositions === null) return

  if (selectedMissionType.value === 'CAPTURE' && !captureTargetPosition) {
    ElMessage.warning('请完整填写围捕目标坐标')
    return
  }

  if (
    selectedMissionType.value === 'ESCORT_DEFENSE' &&
    (!escortTargetPosition || !escortThreatPosition)
  ) {
    ElMessage.warning('请完整填写护航目标和威胁目标坐标')
    return
  }

  starting.value = true
  try {
    const sourcePayload =
      positionSource.value === 'MANUAL'
        ? {
            positionSource: 'MANUAL' as const,
            manualVehiclePositions: manualPositions,
          }
        : {
            positionSource: 'REALTIME' as const,
          }
    const payload: AlgorithmStartPayload =
      selectedMissionType.value === 'CAPTURE'
        ? {
            algorithmType: 'CAPTURE',
            targetId: captureForm.targetId,
            targetPosition: captureTargetPosition ?? undefined,
            uavIds: [...captureForm.uavIds],
            usvIds: [...captureForm.usvIds],
            ...sourcePayload,
            parameters: {
              captureRadius: captureForm.captureRadius,
              minimumAgents: captureForm.minimumAgents,
              dynamicReassignment: captureForm.dynamicReassignment,
            },
          }
        : {
            algorithmType: 'ESCORT_DEFENSE',
            targetId: escortForm.escortTargetId,
            targetPosition: escortTargetPosition ?? undefined,
            threatPosition: escortThreatPosition ?? undefined,
            uavIds: [...escortForm.uavIds],
            usvIds: [...escortForm.usvIds],
            ...sourcePayload,
            parameters: {
              escortTargetId: escortForm.escortTargetId,
              threatTargetId: escortForm.threatTargetId,
              escortRadius: escortForm.escortRadius,
              defenseDistance: escortForm.defenseDistance,
              threatDirection: escortForm.threatDirection,
            },
          }
    const run = await algorithmStore.start(payload)

    startDemo(run.commandId, {
      positionSource: positionSource.value,
      vehicleIds: selectedVehicleIds.value,
      manualVehiclePositions: positionSource.value === 'MANUAL' ? manualPositions : [],
    })
    ElMessage.success(`算法指令已提交，真实Python算法服务已返回：${run.commandId}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '算法指令提交失败')
  } finally {
    starting.value = false
  }
}

async function handleStop() {
  if (!currentCommandId.value) {
    ElMessage.warning('暂无可停止的算法指令')
    return
  }

  stopping.value = true
  try {
    await algorithmStore.stop({
      commandId: currentCommandId.value,
      reason: '用户从围捕/护航控制面板停止算法',
    })
    stopDemo()
    ElMessage.info('算法停止指令已提交')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '算法停止失败')
  } finally {
    stopping.value = false
  }
}

function handleReset() {
  resetDemo()
  ElMessage.success('算法参数已重置')
}
</script>

<template>
  <section class="console-panel algorithm-control-panel">
    <div class="algorithm-control-heading">
      <div>
        <h2>协同算法控制</h2>
        <p>配置围捕或护航防守任务参数。</p>
      </div>

      <div class="heading-actions">
        <el-tag
          :type="controlStateTagType()"
          effect="plain"
        >
          {{ controlStateLabel() }}
        </el-tag>

        <el-tag type="warning" effect="plain">
          接口已连接
        </el-tag>
      </div>
    </div>

    <el-alert
      title="当前任务将调用真实Python算法服务。"
      description="实时位姿读取 RuntimeDeviceStatus；手动初始位姿实验只使用本页输入作为车辆初始位置。"
      type="info"
      show-icon
      :closable="false"
      class="demo-alert"
    />

    <div class="mission-type-selector">
      <span>任务模式</span>

      <el-radio-group
        v-model="selectedMissionType"
        :disabled="controlState === 'RUNNING' || starting || stopping"
      >
        <el-radio-button value="CAPTURE">
          协同围捕
        </el-radio-button>

        <el-radio-button value="ESCORT_DEFENSE">
          护航防守
        </el-radio-button>
      </el-radio-group>
    </div>

    <div class="mission-type-selector">
      <span>输入来源</span>

      <el-radio-group
        v-model="positionSource"
        :disabled="controlState === 'RUNNING' || starting || stopping"
      >
        <el-radio-button
          v-for="option in sourceOptions"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <el-alert
      :title="
        positionSource === 'MANUAL'
          ? '手动初始位姿实验：车辆初始位置来自本页输入，不读取ROS实时位姿；分配结果仍由真实Python算法计算。'
          : '实时位姿：车辆初始位置来自运行状态，要求设备在线且位姿未过期。'
      "
      :type="positionSource === 'MANUAL' ? 'warning' : 'info'"
      show-icon
      :closable="false"
      class="demo-alert"
    />

    <el-form
      v-if="selectedMissionType === 'CAPTURE'"
      label-position="top"
      class="algorithm-parameter-form"
    >
      <div class="form-grid">
        <el-form-item label="围捕目标">
          <el-input
            v-model="captureForm.targetId"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="例如 target_01"
          />
        </el-form-item>

        <el-form-item label="目标 X">
          <el-input-number
            v-model="captureForm.targetPosition.x"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标 Y">
          <el-input-number
            v-model="captureForm.targetPosition.y"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标 Z">
          <el-input-number
            v-model="captureForm.targetPosition.z"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标航向">
          <el-input-number
            v-model="captureForm.targetPosition.heading"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="围捕半径（m）">
          <el-input-number
            v-model="captureForm.captureRadius"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            :min="10"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="最少围捕平台数">
          <el-input-number
            v-model="captureForm.minimumAgents"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            :min="1"
            :max="20"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="动态重新分配">
          <el-switch
            v-model="captureForm.dynamicReassignment"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            active-text="允许"
            inactive-text="关闭"
          />
        </el-form-item>
      </div>

      <div class="vehicle-grid">
        <el-form-item label="参与UAV">
          <el-select
            v-model="captureForm.uavIds"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择UAV"
          >
            <el-option
              v-for="option in uavOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="参与USV">
          <el-select
            v-model="captureForm.usvIds"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择USV"
          >
            <el-option
              v-for="option in usvOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </div>
    </el-form>

    <el-form
      v-else
      label-position="top"
      class="algorithm-parameter-form"
    >
      <div class="form-grid">
        <el-form-item label="被护航目标">
          <el-input
            v-model="escortForm.escortTargetId"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="例如 escort_target_01"
          />
        </el-form-item>

        <el-form-item label="威胁目标">
          <el-input
            v-model="escortForm.threatTargetId"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="例如 enemy_01"
          />
        </el-form-item>

        <div class="coordinate-section-title">护航目标</div>

        <el-form-item label="目标 X">
          <el-input-number
            v-model="escortForm.targetPosition.x"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标 Y">
          <el-input-number
            v-model="escortForm.targetPosition.y"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标 Z">
          <el-input-number
            v-model="escortForm.targetPosition.z"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="目标航向">
          <el-input-number
            v-model="escortForm.targetPosition.heading"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <div class="coordinate-section-title">威胁目标</div>

        <el-form-item label="威胁 X">
          <el-input-number
            v-model="escortForm.threatPosition.x"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="威胁 Y">
          <el-input-number
            v-model="escortForm.threatPosition.y"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="威胁 Z">
          <el-input-number
            v-model="escortForm.threatPosition.z"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="威胁航向">
          <el-input-number
            v-model="escortForm.threatPosition.heading"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="护航半径（m）">
          <el-input-number
            v-model="escortForm.escortRadius"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            :min="10"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="防御距离（m）">
          <el-input-number
            v-model="escortForm.defenseDistance"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            :min="5"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="威胁方向">
          <el-select
            v-model="escortForm.threatDirection"
            :disabled="controlState === 'RUNNING' || starting || stopping"
          >
            <el-option
              v-for="option in threatDirectionOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </div>

      <div class="vehicle-grid">
        <el-form-item label="参与UAV">
          <el-select
            v-model="escortForm.uavIds"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择UAV"
          >
            <el-option
              v-for="option in uavOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="参与USV">
          <el-select
            v-model="escortForm.usvIds"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择USV"
          >
            <el-option
              v-for="option in usvOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </div>
    </el-form>

    <section
      v-if="positionSource === 'MANUAL'"
      class="manual-position-section"
    >
      <div class="manual-position-group">
        <h3>参与UAV初始位姿</h3>

        <el-empty
          v-if="manualUavRows.length === 0"
          description="未选择UAV"
          :image-size="70"
        />

        <div
          v-for="row in manualUavRows"
          :key="row.vehicleId"
          class="manual-position-row"
        >
          <strong>{{ vehicleLabel(row.vehicleId) }}</strong>

          <el-input-number
            v-model="row.position.x"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="X"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.y"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="Y"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.z"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="Z"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.heading"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="航向(rad)"
            controls-position="right"
          />
        </div>
      </div>

      <div class="manual-position-group">
        <h3>参与USV初始位姿</h3>

        <el-empty
          v-if="manualUsvRows.length === 0"
          description="未选择USV"
          :image-size="70"
        />

        <div
          v-for="row in manualUsvRows"
          :key="row.vehicleId"
          class="manual-position-row"
        >
          <strong>{{ vehicleLabel(row.vehicleId) }}</strong>

          <el-input-number
            v-model="row.position.x"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="X"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.y"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="Y"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.z"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="Z"
            controls-position="right"
          />

          <el-input-number
            v-model="row.position.heading"
            :disabled="controlState === 'RUNNING' || starting || stopping"
            placeholder="航向(rad)"
            controls-position="right"
          />
        </div>
      </div>
    </section>

    <div class="algorithm-control-actions">
      <el-button
        type="primary"
        :disabled="controlState === 'RUNNING' || starting || stopping"
        :loading="starting"
        @click="handleStart"
      >
        启动算法
      </el-button>

      <el-button
        type="danger"
        plain
        :disabled="controlState !== 'RUNNING' || starting || stopping"
        :loading="stopping"
        @click="handleStop"
      >
        停止算法
      </el-button>

      <el-button
        :disabled="controlState === 'RUNNING' || starting || stopping"
        @click="handleReset"
      >
        重置参数
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.algorithm-control-panel {
  margin-bottom: 20px;
  overflow: hidden;
}

.algorithm-control-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.algorithm-control-heading h2 {
  margin: 0;
  font-size: 18px;
}

.algorithm-control-heading p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.demo-alert {
  margin-bottom: 18px;
}

.mission-type-selector {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}

.mission-type-selector > span {
  font-weight: 600;
}

.algorithm-parameter-form {
  padding: 18px;
  border: 1px solid rgba(86, 207, 225, 0.2);
  border-radius: 8px;
  background: rgba(8, 35, 40, 0.32);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.vehicle-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.manual-position-section {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
  padding: 18px;
  border: 1px solid rgba(255, 209, 102, 0.24);
  border-radius: 8px;
  background: rgba(8, 35, 40, 0.32);
}

.manual-position-group {
  min-width: 0;
}

.manual-position-group h3 {
  margin: 0 0 12px;
  font-size: 14px;
}

.manual-position-row {
  display: grid;
  grid-template-columns: minmax(88px, 0.8fr) repeat(4, minmax(0, 1fr));
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.manual-position-row strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coordinate-section-title {
  grid-column: 1 / -1;
  font-size: 13px;
  font-weight: 600;
}

.algorithm-parameter-form :deep(.el-input-number),
.manual-position-section :deep(.el-input-number),
.algorithm-parameter-form :deep(.el-select) {
  width: 100%;
}

.algorithm-control-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

@media (max-width: 1100px) {
  .form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .manual-position-section,
  .manual-position-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .algorithm-control-heading,
  .mission-type-selector {
    align-items: stretch;
    flex-direction: column;
  }

  .form-grid,
  .manual-position-section,
  .manual-position-row,
  .vehicle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
