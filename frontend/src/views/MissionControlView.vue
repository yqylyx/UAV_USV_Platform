<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Eye, Pencil, Plus, RotateCcw, Search, Trash2 } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { createMission, deleteMission, executeMissionAction, fetchMission, updateMission } from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import { fetchDevices } from '@/api/device'
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionTrajectoryMap from '@/components/mission/MissionTrajectoryMap.vue'
import { useAuthStore } from '@/stores/auth'
import { useMissionStore } from '@/stores/mission'
import type { Device } from '@/types/device'
import type {
  Mission,
  MissionDetail,
  MissionDeviceRole,
  MissionRunStatus,
  MissionSavePayload,
  MissionStage,
  MissionStatus,
  MissionType,
} from '@/types/mission'

const authStore = useAuthStore()
const missionStore = useMissionStore()
const formRef = ref<FormInstance>()
const dialogVisible = ref(false)
const detailVisible = ref(false)
const deleteDialogVisible = ref(false)
const saving = ref(false)
const detailLoading = ref(false)
const deletingId = ref<number | null>(null)
const actionLoadingId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const detail = ref<MissionDetail | null>(null)
const deleteTarget = ref<Mission | null>(null)
const deviceOptions = ref<Device[]>([])

const filters = reactive({
  keyword: '',
  type: '' as MissionType | '',
  status: '' as MissionStatus | '',
})

const form = reactive<MissionSavePayload>({
  code: '',
  name: '',
  type: 'COOPERATIVE_ENCIRCLEMENT',
  status: 'DRAFT',
  stage: 'PREPARE',
  priority: 3,
  targetName: '',
  targetBehavior: '',
  missionArea: '',
  plannedStartAt: null,
  plannedEndAt: null,
  description: '',
  devices: [],
  parameters: [],
})

const rules: FormRules<MissionSavePayload> = {
  code: [{ required: true, message: '请输入任务编号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择任务状态', trigger: 'change' }],
  stage: [{ required: true, message: '请选择任务阶段', trigger: 'change' }],
}

const typeOptions: Array<{ label: string; value: MissionType }> = [
  { label: '目标巡检', value: 'TARGET_INSPECTION' },
  { label: '协同围捕', value: 'COOPERATIVE_ENCIRCLEMENT' },
  { label: '路径跟踪', value: 'PATH_TRACKING' },
  { label: '通信中继', value: 'COMMUNICATION_RELAY' },
  { label: '自定义任务', value: 'CUSTOM' },
]

const statusOptions: Array<{ label: string; value: MissionStatus }> = [
  { label: '草稿', value: 'DRAFT' },
  { label: '待执行', value: 'READY' },
  { label: '运行中', value: 'RUNNING' },
  { label: '已暂停', value: 'PAUSED' },
  { label: '已完成', value: 'COMPLETED' },
  { label: '异常', value: 'FAILED' },
  { label: '已取消', value: 'CANCELLED' },
]

const editableStatusOptions = statusOptions.filter((item) => item.value === 'DRAFT' || item.value === 'READY')

const stageOptions: Array<{ label: string; value: MissionStage }> = [
  { label: '任务准备', value: 'PREPARE' },
  { label: '目标发现', value: 'TARGET_DETECTED' },
  { label: '任务分配', value: 'ASSIGNMENT' },
  { label: '协同跟踪', value: 'TRACKING' },
  { label: '合围控制', value: 'ENCIRCLEMENT' },
  { label: '目标捕获', value: 'CAPTURED' },
  { label: '评估回放', value: 'EVALUATION' },
]

const roleOptions: Array<{ label: string; value: MissionDeviceRole }> = [
  { label: '指挥单元', value: 'LEADER' },
  { label: 'UAV 侦察', value: 'UAV_RECON' },
  { label: 'UAV 跟踪', value: 'UAV_TRACK' },
  { label: 'USV 拦截', value: 'USV_INTERCEPT' },
  { label: 'USV 封控', value: 'USV_BLOCKADE' },
  { label: 'ROS 网关', value: 'ROS_BRIDGE' },
  { label: 'Unity 态势端', value: 'UNITY_CLIENT' },
]

const canManage = computed(() => authStore.user?.role === 'ADMIN')
const dialogTitle = computed(() => (editingId.value ? '编辑任务配置' : '新建协同任务'))
const runningCount = computed(() => missionStore.records.filter((item) => item.status === 'RUNNING').length)
const readyCount = computed(() => missionStore.records.filter((item) => item.status === 'READY').length)
const failedCount = computed(() => missionStore.records.filter((item) => item.status === 'FAILED').length)
const currentMission = computed(() => missionStore.records.find((item) => item.status === 'RUNNING') ?? missionStore.records[0] ?? null)
const encirclementCount = computed(
  () => missionStore.records.filter((item) => item.type === 'COOPERATIVE_ENCIRCLEMENT').length,
)

function typeLabel(type: MissionType) {
  return typeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: MissionStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function runStatusLabel(status: MissionRunStatus) {
  if (status === 'PENDING') return '等待确认'
  return statusLabel(status as MissionStatus)
}

function stageLabel(stage: MissionStage) {
  return stageOptions.find((item) => item.value === stage)?.label ?? stage
}

function roleLabel(role: MissionDeviceRole) {
  return roleOptions.find((item) => item.value === role)?.label ?? role
}

function statusClass(status: MissionStatus) {
  return status.toLowerCase().replace('_', '-')
}

function statusTag(status: MissionStatus) {
  if (status === 'RUNNING' || status === 'COMPLETED') return 'success'
  if (status === 'READY' || status === 'PAUSED') return 'warning'
  if (status === 'FAILED' || status === 'CANCELLED') return 'danger'
  return 'info'
}

function missionActions(status: MissionStatus): Array<{ action: MissionAction; label: string; type: 'primary' | 'warning' | 'success' | 'danger' }> {
  if (status === 'DRAFT') return [{ action: 'ready', label: '准备', type: 'primary' }]
  if (status === 'READY') {
    return [
      { action: 'start', label: '启动', type: 'success' },
      { action: 'cancel', label: '取消', type: 'danger' },
    ]
  }
  if (status === 'RUNNING') {
    return [
      { action: 'pause', label: '暂停', type: 'warning' },
      { action: 'complete', label: '完成', type: 'success' },
      { action: 'fail', label: '异常', type: 'danger' },
    ]
  }
  if (status === 'PAUSED') {
    return [
      { action: 'resume', label: '恢复', type: 'success' },
      { action: 'complete', label: '完成', type: 'primary' },
      { action: 'cancel', label: '取消', type: 'danger' },
    ]
  }
  return []
}

function formatTime(value: string | null) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function resetForm() {
  editingId.value = null
  Object.assign(form, {
    code: `MT-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${String(Date.now()).slice(-3)}`,
    name: '',
    type: 'COOPERATIVE_ENCIRCLEMENT',
    status: 'DRAFT',
    stage: 'PREPARE',
    priority: 3,
    targetName: '灯塔目标',
    targetBehavior: '无人机从无人艇甲板起飞，无人艇朝灯塔方向推进',
    missionArea: '近海协同仿真海域',
    plannedStartAt: null,
    plannedEndAt: null,
    description: '',
    devices: [],
    parameters: [
      { key: 'takeoff_height', value: '2.5', unit: 'm', description: '无人机垂直起飞高度' },
      { key: 'approach_speed', value: '1.2', unit: 'm/s', description: '无人艇接近灯塔速度' },
    ],
  })
  formRef.value?.clearValidate()
}

async function loadDevices() {
  const result = await fetchDevices({ page: 0, size: 100 })
  deviceOptions.value = result.records
}

async function load(page = 0) {
  missionStore.keyword = filters.keyword.trim()
  missionStore.type = filters.type || undefined
  missionStore.status = filters.status || undefined
  await missionStore.refresh({ page })
}

async function resetFilters() {
  filters.keyword = ''
  filters.type = ''
  filters.status = ''
  await load(0)
}

async function openCreate() {
  resetForm()
  if (deviceOptions.value.length === 0) await loadDevices()
  dialogVisible.value = true
}

async function openEdit(row: Mission | Record<string, unknown>) {
  const mission = row as Mission
  if (deviceOptions.value.length === 0) await loadDevices()
  detailLoading.value = true
  try {
    const result = await fetchMission(mission.id)
    editingId.value = mission.id
    Object.assign(form, {
      code: result.mission.code,
      name: result.mission.name,
      type: result.mission.type,
      status: result.mission.status,
      stage: result.mission.stage,
      priority: result.mission.priority,
      targetName: result.mission.targetName ?? '',
      targetBehavior: result.mission.targetBehavior ?? '',
      missionArea: result.mission.missionArea ?? '',
      plannedStartAt: result.mission.plannedStartAt,
      plannedEndAt: result.mission.plannedEndAt,
      description: result.mission.description ?? '',
      devices: result.devices.map((item) => ({
        deviceId: item.deviceId,
        role: item.role,
        callSign: item.callSign ?? '',
        required: item.required,
        notes: item.notes ?? '',
      })),
      parameters: result.parameters.map((item) => ({
        key: item.key,
        value: item.value ?? '',
        unit: item.unit ?? '',
        description: item.description ?? '',
      })),
    })
    dialogVisible.value = true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function openDetail(row: Mission | Record<string, unknown>) {
  const mission = row as Mission
  detailLoading.value = true
  detailVisible.value = true
  try {
    detail.value = await fetchMission(mission.id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function addDeviceBinding() {
  const firstDevice = deviceOptions.value[0]
  form.devices.push({
    deviceId: firstDevice?.id ?? 0,
    role: firstDevice?.type === 'USV' ? 'USV_INTERCEPT' : firstDevice?.type === 'ROS_NODE' ? 'ROS_BRIDGE' : 'UAV_RECON',
    callSign: firstDevice?.code ?? '',
    required: true,
    notes: '',
  })
}

function removeDeviceBinding(index: number) {
  form.devices.splice(index, 1)
}

function addParameter() {
  form.parameters.push({ key: '', value: '', unit: '', description: '' })
}

function removeParameter(index: number) {
  form.parameters.splice(index, 1)
}

function openDelete(row: Mission | Record<string, unknown>) {
  deleteTarget.value = row as Mission
  deleteDialogVisible.value = true
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  try {
    deletingId.value = deleteTarget.value.id
    await deleteMission(deleteTarget.value.id)
    ElMessage.success('任务已删除')
    deleteDialogVisible.value = false
    deleteTarget.value = null
    await load(Math.max(0, missionStore.records.length === 1 ? missionStore.page - 1 : missionStore.page))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  } finally {
    deletingId.value = null
  }
}

async function runMissionAction(row: Mission | Record<string, unknown>, action: MissionAction) {
  const mission = row as Mission
  actionLoadingId.value = mission.id
  try {
    const result = await executeMissionAction(mission.id, action)
    const latest = result.detail
    detail.value = detail.value?.mission.id === mission.id ? latest : detail.value
    if (result.command?.status === 'DISPATCHED' || result.command?.status === 'PENDING') {
      ElMessage.warning(`${latest.mission.name}：指令已下发，等待外部组件确认`)
    } else if (result.command?.status === 'FAILED' || result.command?.status === 'TIMEOUT') {
      ElMessage.error(`${latest.mission.name}：${result.command.detail || '控制指令执行失败'}`)
    } else {
      ElMessage.success(`${latest.mission.name}：${statusLabel(latest.mission.status)}`)
    }
    await load(missionStore.page)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '任务状态变更失败')
  } finally {
    actionLoadingId.value = null
  }
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (form.devices.some((item) => !item.deviceId)) {
    ElMessage.warning('请补全任务设备编组')
    return
  }

  saving.value = true
  try {
    const payload: MissionSavePayload = {
      ...form,
      devices: form.devices.filter((item) => item.deviceId),
      parameters: form.parameters.filter((item) => item.key.trim()),
    }
    if (editingId.value) {
      await updateMission(editingId.value, payload)
      ElMessage.success('任务配置已更新')
    } else {
      await createMission(payload)
      ElMessage.success('任务已创建')
    }
    dialogVisible.value = false
    await load(missionStore.page)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(0), loadDevices()])
})
</script>

<template>
  <ConsoleLayout title="任务控制" eyebrow="MISSION COMMAND">
    <template #actions>
      <el-button v-if="canManage" type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
    </template>

    <el-alert
      v-if="missionStore.error"
      title="任务数据加载失败"
      :description="missionStore.error"
      type="error"
      show-icon
      :closable="false"
      class="section-alert"
    />

    <section class="mission-command-layout">
      <article class="console-panel mission-map-panel">
        <div class="panel-heading">
          <div>
            <h2>协同围捕轨迹地图</h2>
            <p>按 Unity 场景的 X/Z 坐标与三角合围逻辑，在 Vue 中独立绘制定位轨迹。</p>
          </div>
          <div class="mission-map-actions">
            <el-button v-if="currentMission" type="primary" @click="runMissionAction(currentMission, currentMission.status === 'DRAFT' ? 'ready' : 'start')">
              下发任务
            </el-button>
            <el-button @click="openCreate">保存方案</el-button>
          </div>
        </div>
        <MissionTrajectoryMap
          :mission-name="currentMission?.name || '三机三艇协同围捕预演'"
          :mission-status="currentMission?.status || 'READY'"
        />
      </article>

      <aside class="mission-side-stack">
        <article class="console-panel mission-state-card">
          <span>任务状态</span>
          <strong>{{ currentMission ? statusLabel(currentMission.status) : '待配置' }}</strong>
          <small>{{ currentMission?.name || '暂无可执行任务' }}</small>
        </article>
        <article class="console-panel mission-steps-card">
          <h3>任务阶段</h3>
          <div class="mission-step-row active">
            <b>1</b>
            <span><strong>无人机起飞</strong><small>从无人艇甲板垂直起飞</small></span>
            <em>READY</em>
          </div>
          <div class="mission-step-row">
            <b>2</b>
            <span><strong>目标接近</strong><small>无人艇朝灯塔方向推进</small></span>
            <em>WAIT</em>
          </div>
          <div class="mission-step-row">
            <b>3</b>
            <span><strong>协同围捕</strong><small>UAV 补盲，USV 收敛</small></span>
            <em>WAIT</em>
          </div>
        </article>
        <article class="console-panel mission-command-card">
          <h3>控制指令</h3>
          <div class="mission-command-buttons">
            <el-button type="primary" @click="currentMission && runMissionAction(currentMission, 'start')">起飞</el-button>
            <el-button @click="currentMission && runMissionAction(currentMission, 'cancel')">返航</el-button>
            <el-button @click="currentMission && runMissionAction(currentMission, 'pause')">暂停</el-button>
            <el-button type="danger" @click="currentMission && runMissionAction(currentMission, 'fail')">终止</el-button>
          </div>
        </article>
      </aside>
    </section>

    <section class="page-metric-grid">
      <article class="console-stat-card">
        <span>任务总数</span>
        <strong>{{ missionStore.total }}</strong>
      </article>
      <article class="console-stat-card">
        <span>围捕任务</span>
        <strong>{{ encirclementCount }}</strong>
      </article>
      <article class="console-stat-card warning">
        <span>待执行</span>
        <strong>{{ readyCount }}</strong>
      </article>
      <article class="console-stat-card danger">
        <span>异常任务</span>
        <strong>{{ failedCount }}</strong>
      </article>
    </section>

    <section class="console-panel filter-panel">
      <el-input v-model="filters.keyword" clearable placeholder="搜索编号、名称、目标或任务区域" @keyup.enter="load(0)" />
      <el-select v-model="filters.type" clearable placeholder="任务类型">
        <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="任务状态">
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button type="primary" :icon="Search" :loading="missionStore.loading" @click="load(0)">查询</el-button>
      <el-button :icon="RotateCcw" @click="resetFilters">重置</el-button>
    </section>

    <section class="console-panel table-panel">
      <div class="panel-heading">
        <div>
          <h2>指令队列</h2>
          <p>这里管理任务方案和任务状态，下发结果会同步到运行控制日志。</p>
        </div>
        <el-tag effect="plain">运行中 {{ runningCount }}</el-tag>
      </div>

      <el-table v-loading="missionStore.loading || detailLoading" :data="missionStore.records" class="console-table">
        <el-table-column label="任务" min-width="180">
          <template #default="{ row }">
            <div class="asset-name-cell">
              <span class="asset-mini-mark mission">{{ row.priority }}</span>
              <div>
                <strong>{{ row.name }}</strong>
                <small>{{ row.code }}</small>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" min-width="80">
          <template #default="{ row }">{{ typeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="阶段" min-width="70">
          <template #default="{ row }">{{ stageLabel(row.stage) }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="70">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标 / 区域" min-width="120">
          <template #default="{ row }">{{ row.targetName || '--' }} / {{ row.missionArea || '--' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="350" fixed="right">
          <template #default="{ row }">
            <span class="action-row">
            <el-button link type="primary" :icon="Eye" @click="openDetail(row)">详情</el-button>
            <template v-if="canManage">
              <el-button
                link
                v-for="item in missionActions(row.status)"
                :key="item.action"
                :type="item.type"
                :loading="actionLoadingId === row.id"
                @click="runMissionAction(row, item.action)"
              >
                {{ item.label }}
              </el-button>
              <el-button link type="primary" :icon="Pencil" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" :icon="Trash2" :loading="deletingId === row.id" @click="openDelete(row)">删除</el-button>
            </template>
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-footer">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="missionStore.total"
          :current-page="missionStore.page + 1"
          :page-size="missionStore.size"
          :page-sizes="[6, 10, 20, 50]"
          @current-change="(page: number) => load(page - 1)"
          @size-change="(size: number) => { missionStore.size = size; load(0) }"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="920px" class="mission-dialog" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="任务编号" prop="code"><el-input v-model="form.code" /></el-form-item>
          <el-form-item label="任务名称" prop="name"><el-input v-model="form.name" placeholder="例如 无人艇协同接近灯塔任务" /></el-form-item>
          <el-form-item label="任务类型" prop="type">
            <el-select v-model="form.type"><el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="任务状态" prop="status">
            <el-select v-model="form.status"><el-option v-for="item in editableStatusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="5" controls-position="right" class="full-control" /></el-form-item>
          <el-form-item label="目标名称"><el-input v-model="form.targetName" /></el-form-item>
          <el-form-item label="任务区域"><el-input v-model="form.missionArea" /></el-form-item>
        </div>
        <el-form-item label="目标行为"><el-input v-model="form.targetBehavior" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="任务说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>

        <div class="dialog-block">
          <div class="dialog-block-head">
            <strong>设备编组</strong>
            <el-button link type="primary" :icon="Plus" @click="addDeviceBinding">添加设备</el-button>
          </div>
          <div v-if="form.devices.length === 0" class="empty-inline">尚未绑定设备</div>
          <div v-for="(binding, index) in form.devices" :key="index" class="binding-row">
            <el-select v-model="binding.deviceId" placeholder="选择设备">
              <el-option v-for="device in deviceOptions" :key="device.id" :label="`${device.name} / ${device.code}`" :value="device.id" />
            </el-select>
            <el-select v-model="binding.role" placeholder="任务角色">
              <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-input v-model="binding.callSign" placeholder="呼号" />
            <el-checkbox v-model="binding.required">必要节点</el-checkbox>
            <el-button link type="danger" :icon="Trash2" @click="removeDeviceBinding(index)">移除</el-button>
          </div>
        </div>

        <div class="dialog-block">
          <div class="dialog-block-head">
            <strong>任务参数</strong>
            <el-button link type="primary" :icon="Plus" @click="addParameter">添加参数</el-button>
          </div>
          <div v-for="(parameter, index) in form.parameters" :key="index" class="parameter-row">
            <el-input v-model="parameter.key" placeholder="参数键" />
            <el-input v-model="parameter.value" placeholder="参数值" />
            <el-input v-model="parameter.unit" placeholder="单位" />
            <el-input v-model="parameter.description" placeholder="说明" />
            <el-button link type="danger" :icon="Trash2" @click="removeParameter(index)">移除</el-button>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存任务</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="任务详情" size="520px" class="mission-detail-drawer">
      <div v-loading="detailLoading" v-if="detail" class="mission-detail">
        <div class="detail-hero">
          <span>{{ detail.mission.code }}</span>
          <strong>{{ detail.mission.name }}</strong>
          <el-tag :type="statusTag(detail.mission.status)" effect="dark">{{ statusLabel(detail.mission.status) }}</el-tag>
        </div>
        <dl class="detail-grid">
          <div><dt>任务类型</dt><dd>{{ typeLabel(detail.mission.type) }}</dd></div>
          <div><dt>任务阶段</dt><dd>{{ stageLabel(detail.mission.stage) }}</dd></div>
          <div><dt>目标</dt><dd>{{ detail.mission.targetName || '--' }}</dd></div>
          <div><dt>海域</dt><dd>{{ detail.mission.missionArea || '--' }}</dd></div>
        </dl>
        <section>
          <h3>执行批次</h3>
          <div v-if="detail.runs.length === 0" class="empty-inline">尚未执行</div>
          <div v-for="run in detail.runs" :key="run.id" class="detail-param">
            <span>第 {{ run.runNo }} 次 / {{ stageLabel(run.stage) }}</span>
            <strong>{{ runStatusLabel(run.status) }} · {{ formatTime(run.startedAt) }}</strong>
          </div>
        </section>
        <section>
          <h3>设备编组</h3>
          <div v-for="device in detail.devices" :key="device.id" class="detail-device">
            <span>{{ device.name || device.code || '未知设备' }}</span>
            <strong>{{ roleLabel(device.role) }}</strong>
          </div>
        </section>
        <section>
          <h3>任务参数</h3>
          <div v-for="parameter in detail.parameters" :key="parameter.id" class="detail-param">
            <span>{{ parameter.key }}</span>
            <strong>{{ parameter.value || '--' }} {{ parameter.unit || '' }}</strong>
          </div>
        </section>
      </div>
    </el-drawer>

    <el-dialog v-model="deleteDialogVisible" title="删除任务" width="460px">
      <div v-if="deleteTarget" class="delete-mission">
        <el-alert title="此操作会把任务从任务控制列表中删除" type="warning" show-icon :closable="false" />
        <p>{{ deleteTarget.name }}</p>
      </div>
      <template #footer>
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" :icon="Trash2" :loading="deletingId !== null" @click="confirmDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </ConsoleLayout>
</template>
