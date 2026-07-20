<script setup lang="ts">
import { ElMessage } from 'element-plus'

import { useAlgorithmMissionDemo } from '@/composables/useAlgorithmMissionDemo'

const {
  selectedMissionType,
  controlState,
  captureForm,
  escortForm,
  startDemo,
  stopDemo,
  resetDemo,
} = useAlgorithmMissionDemo()

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

function validateCaptureForm() {
  if (!captureForm.targetId.trim()) {
    ElMessage.warning('请选择或填写围捕目标')
    return false
  }

  const totalAgents =
    captureForm.uavIds.length + captureForm.usvIds.length

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

  if (
    escortForm.uavIds.length === 0 &&
    escortForm.usvIds.length === 0
  ) {
    ElMessage.warning('请至少选择一个参与平台')
    return false
  }

  return true
}

function handleStart() {
  const valid =
    selectedMissionType.value === 'CAPTURE'
      ? validateCaptureForm()
      : validateEscortForm()

  if (!valid) return

  startDemo()

  ElMessage.success(
    selectedMissionType.value === 'CAPTURE'
      ? '围捕前端演示已启动，未调用真实算法'
      : '护航防守前端演示已启动，未调用真实算法',
  )
}

function handleStop() {
  stopDemo()
  ElMessage.info('前端演示已停止，未向真实算法发送指令')
}

function handleReset() {
  resetDemo()
  ElMessage.success('算法演示参数已重置')
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
          前端演示
        </el-tag>
      </div>
    </div>

    <el-alert
      title="当前为前端演示模式"
      description="启动和停止按钮只验证页面交互，没有调用Python算法、ROS、后端或Unity。"
      type="warning"
      show-icon
      :closable="false"
      class="demo-alert"
    />

    <div class="mission-type-selector">
      <span>任务模式</span>

      <el-radio-group
        v-model="selectedMissionType"
        :disabled="controlState === 'RUNNING'"
      >
        <el-radio-button value="CAPTURE">
          协同围捕
        </el-radio-button>

        <el-radio-button value="ESCORT_DEFENSE">
          护航防守
        </el-radio-button>
      </el-radio-group>
    </div>

    <el-form
      v-if="selectedMissionType === 'CAPTURE'"
      label-position="top"
      class="algorithm-parameter-form"
    >
      <div class="form-grid">
        <el-form-item label="围捕目标">
          <el-input
            v-model="captureForm.targetId"
            :disabled="controlState === 'RUNNING'"
            placeholder="例如 target_01"
          />
        </el-form-item>

        <el-form-item label="围捕半径（m）">
          <el-input-number
            v-model="captureForm.captureRadius"
            :disabled="controlState === 'RUNNING'"
            :min="10"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="最少围捕平台数">
          <el-input-number
            v-model="captureForm.minimumAgents"
            :disabled="controlState === 'RUNNING'"
            :min="1"
            :max="20"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="动态重新分配">
          <el-switch
            v-model="captureForm.dynamicReassignment"
            :disabled="controlState === 'RUNNING'"
            active-text="允许"
            inactive-text="关闭"
          />
        </el-form-item>
      </div>

      <div class="vehicle-grid">
        <el-form-item label="参与UAV">
          <el-select
            v-model="captureForm.uavIds"
            :disabled="controlState === 'RUNNING'"
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
            :disabled="controlState === 'RUNNING'"
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
            :disabled="controlState === 'RUNNING'"
            placeholder="例如 escort_target_01"
          />
        </el-form-item>

        <el-form-item label="威胁目标">
          <el-input
            v-model="escortForm.threatTargetId"
            :disabled="controlState === 'RUNNING'"
            placeholder="例如 enemy_01"
          />
        </el-form-item>

        <el-form-item label="护航半径（m）">
          <el-input-number
            v-model="escortForm.escortRadius"
            :disabled="controlState === 'RUNNING'"
            :min="10"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="防守距离（m）">
          <el-input-number
            v-model="escortForm.defenseDistance"
            :disabled="controlState === 'RUNNING'"
            :min="5"
            :max="500"
            :step="5"
            controls-position="right"
          />
        </el-form-item>

        <el-form-item label="威胁方向">
          <el-select
            v-model="escortForm.threatDirection"
            :disabled="controlState === 'RUNNING'"
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
            :disabled="controlState === 'RUNNING'"
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
            :disabled="controlState === 'RUNNING'"
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

    <div class="algorithm-control-actions">
      <el-button
        type="primary"
        :disabled="controlState === 'RUNNING'"
        @click="handleStart"
      >
        启动算法演示
      </el-button>

      <el-button
        type="danger"
        plain
        :disabled="controlState !== 'RUNNING'"
        @click="handleStop"
      >
        停止演示
      </el-button>

      <el-button
        :disabled="controlState === 'RUNNING'"
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

.algorithm-parameter-form :deep(.el-input-number),
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
}

@media (max-width: 720px) {
  .algorithm-control-heading,
  .mission-type-selector {
    align-items: stretch;
    flex-direction: column;
  }

  .form-grid,
  .vehicle-grid {
    grid-template-columns: 1fr;
  }
}
</style>