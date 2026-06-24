<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  CalendarClock,
  Eye,
  Pencil,
  Plus,
  Radar,
  RotateCcw,
  Search,
  ShieldAlert,
  Trash2,
  UsersRound,
} from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { createMission, deleteMission, fetchMission, updateMission } from '@/api/mission'
import { fetchDevices } from '@/api/device'
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { useMissionStore } from '@/stores/mission'
import type { Device } from '@/types/device'
import type {
  Mission,
  MissionDetail,
  MissionDeviceRole,
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
const encirclementCount = computed(
  () => missionStore.records.filter((item) => item.type === 'COOPERATIVE_ENCIRCLEMENT').length,
)

function typeLabel(type: MissionType) {
  return typeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: MissionStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
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
    targetName: '海面机动目标',
    targetBehavior: '',
    missionArea: '',
    plannedStartAt: null,
    plannedEndAt: null,
    description: '',
    devices: [],
    parameters: [
      { key: 'encirclement_radius', value: '35', unit: 'm', description: '目标围捕半径' },
      { key: 'heartbeat_timeout', value: '10', unit: 's', description: '节点心跳超时阈值' },
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

async function openEdit(mission: Mission) {
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

async function openDetail(mission: Mission) {
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

function openDelete(mission: Mission) {
  deleteTarget.value = mission
  deleteDialogVisible.value = true
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  try {
    deletingId.value = deleteTarget.value.id
    await deleteMission(deleteTarget.value.id)
    ElMessage.success('任务已隐藏')
    deleteDialogVisible.value = false
    deleteTarget.value = null
    await load(Math.max(0, missionStore.records.length === 1 ? missionStore.page - 1 : missionStore.page))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  } finally {
    deletingId.value = null
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
  <ConsoleLayout title="任务控制" eyebrow="MISSION CONTROL">
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

    <section class="mission-command">
      <div class="mission-command-copy">
        <p>COOPERATIVE ENCIRCLEMENT</p>
        <h2>三机三艇协同围捕任务指挥台</h2>
        <span>把任务类型、目标、海域、UAV / USV 编组、ROS 与 Unity 链路统一登记，为后续算法决策、任务启动和评估回放提供数据底座。</span>
      </div>
      <div class="mission-command-metrics">
        <div>
          <Radar :size="18" />
          <strong>{{ missionStore.total }}</strong>
          <span>任务总数</span>
        </div>
        <div>
          <UsersRound :size="18" />
          <strong>{{ encirclementCount }}</strong>
          <span>围捕任务</span>
        </div>
        <div>
          <CalendarClock :size="18" />
          <strong>{{ readyCount }}</strong>
          <span>待执行</span>
        </div>
        <div>
          <ShieldAlert :size="18" />
          <strong>{{ failedCount }}</strong>
          <span>异常任务</span>
        </div>
      </div>
    </section>

    <section class="mission-filter-panel">
      <div class="mission-filter-fields">
        <el-input v-model="filters.keyword" clearable placeholder="搜索编号、名称、目标或任务区域" @keyup.enter="load(0)" />
        <el-select v-model="filters.type" clearable placeholder="任务类型">
          <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="任务状态">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>
      <div class="mission-filter-actions">
        <el-button type="primary" :icon="Search" :loading="missionStore.loading" @click="load(0)">查询</el-button>
        <el-button :icon="RotateCcw" @click="resetFilters">重置</el-button>
      </div>
    </section>

    <section class="mission-section">
      <div class="section-heading">
        <div>
          <h2>任务编组</h2>
          <p>先管理任务方案和设备编队，后续再接 ROS 启动、Unity 态势和算法服务。</p>
        </div>
        <el-tag effect="plain">运行中 {{ runningCount }}</el-tag>
      </div>

      <div v-loading="missionStore.loading || detailLoading" class="mission-grid">
        <el-empty v-if="!missionStore.loading && missionStore.records.length === 0" description="暂无任务" />
        <template v-else>
          <article
            v-for="mission in missionStore.records"
            :key="mission.id"
            class="mission-card"
            :class="statusClass(mission.status)"
          >
            <div class="mission-card-head">
              <div>
                <span>{{ mission.code }}</span>
                <strong>{{ mission.name }}</strong>
              </div>
              <i>{{ statusLabel(mission.status) }}</i>
            </div>
            <div class="mission-card-body">
              <div>
                <span>任务类型</span>
                <strong>{{ typeLabel(mission.type) }}</strong>
              </div>
              <div>
                <span>任务阶段</span>
                <strong>{{ stageLabel(mission.stage) }}</strong>
              </div>
              <div>
                <span>目标</span>
                <strong>{{ mission.targetName || '--' }}</strong>
              </div>
              <div>
                <span>任务海域</span>
                <strong>{{ mission.missionArea || '--' }}</strong>
              </div>
            </div>
            <div class="mission-card-strip">
              <span>设备 {{ mission.deviceCount }}</span>
              <span>优先级 {{ mission.priority }}</span>
              <span>{{ formatTime(mission.plannedStartAt) }} - {{ formatTime(mission.plannedEndAt) }}</span>
            </div>
            <div class="mission-card-actions">
              <el-button link type="primary" :icon="Eye" @click="openDetail(mission)">详情</el-button>
              <el-button v-if="canManage" link type="primary" :icon="Pencil" @click="openEdit(mission)">编辑</el-button>
              <el-button
                v-if="canManage"
                link
                type="danger"
                :icon="Trash2"
                :loading="deletingId === mission.id"
                @click="openDelete(mission)"
              >
                删除
              </el-button>
            </div>
          </article>
        </template>
      </div>

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
          <el-form-item label="任务名称" prop="name"><el-input v-model="form.name" placeholder="例如 三机三艇协同围捕任务" /></el-form-item>
          <el-form-item label="任务类型" prop="type">
            <el-select v-model="form.type"><el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="任务状态" prop="status">
            <el-select v-model="form.status"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="任务阶段" prop="stage">
            <el-select v-model="form.stage"><el-option v-for="item in stageOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="5" controls-position="right" class="full-control" /></el-form-item>
          <el-form-item label="目标名称"><el-input v-model="form.targetName" /></el-form-item>
          <el-form-item label="任务区域"><el-input v-model="form.missionArea" /></el-form-item>
          <el-form-item label="计划开始"><el-date-picker v-model="form.plannedStartAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" class="full-control" /></el-form-item>
          <el-form-item label="计划结束"><el-date-picker v-model="form.plannedEndAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" class="full-control" /></el-form-item>
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
              <el-option
                v-for="device in deviceOptions"
                :key="device.id"
                :label="`${device.name} / ${device.code}`"
                :value="device.id"
              />
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
        <section>
          <h3>事件时间线</h3>
          <el-timeline>
            <el-timeline-item v-for="event in detail.events" :key="event.id" :timestamp="formatTime(event.occurredAt)">
              <strong>{{ event.title }}</strong>
              <p>{{ event.message }}</p>
            </el-timeline-item>
          </el-timeline>
        </section>
      </div>
    </el-drawer>

    <el-dialog v-model="deleteDialogVisible" title="删除任务" width="460px">
      <div v-if="deleteTarget" class="delete-mission">
        <el-alert
          title="此操作会把任务从任务控制列表中隐藏"
          description="历史事件和设备编组记录会保留，后续评估回放仍可基于数据库恢复。"
          type="warning"
          show-icon
          :closable="false"
        />
        <p>{{ deleteTarget.name }}</p>
      </div>
      <template #footer>
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" :icon="Trash2" :loading="deletingId !== null" @click="confirmDelete">确认删除</el-button>
      </template>
    </el-dialog>
  </ConsoleLayout>
</template>

<style scoped>
.mission-command {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: stretch;
  margin-bottom: 18px;
  padding: 26px 28px;
  border: 1px solid rgba(77, 219, 205, 0.32);
  border-radius: 8px;
  background:
    linear-gradient(rgba(77, 219, 205, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(77, 219, 205, 0.06) 1px, transparent 1px),
    #061d20;
  background-size: 34px 34px;
  color: #e8fffb;
}

.mission-command-copy p,
.mission-command-copy span {
  margin: 0;
  color: #72f4e6;
  font-size: 12px;
  font-weight: 700;
}

.mission-command-copy h2 {
  margin: 8px 0 8px;
  font-size: 32px;
  letter-spacing: 0;
}

.mission-command-copy span {
  display: block;
  max-width: 820px;
  color: #a9c6c9;
  line-height: 1.8;
}

.mission-command-metrics {
  display: grid;
  grid-template-columns: repeat(4, 120px);
  gap: 12px;
}

.mission-command-metrics div {
  display: grid;
  place-items: center;
  min-height: 88px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
}

.mission-command-metrics strong {
  font-size: 24px;
  color: #ffc861;
}

.mission-command-metrics span {
  color: #84d8d4;
  font-size: 12px;
}

.mission-filter-panel {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 22px;
  padding: 12px;
  border: 1px solid #d7e3e7;
  border-radius: 8px;
  background: #fff;
}

.mission-filter-fields {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 180px 180px;
  gap: 10px;
  width: 100%;
}

.mission-filter-actions {
  display: flex;
  gap: 10px;
  flex: 0 0 auto;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-heading h2 {
  margin: 0;
  font-size: 20px;
}

.section-heading p {
  margin: 4px 0 0;
  color: #66808a;
}

.mission-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(280px, 1fr));
  gap: 14px;
  min-height: 220px;
}

.mission-card {
  overflow: hidden;
  border: 1px solid #d8e5e9;
  border-top: 4px solid #4dd9cd;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(16, 40, 48, 0.06);
}

.mission-card.running {
  border-top-color: #46c778;
}

.mission-card.failed,
.mission-card.cancelled {
  border-top-color: #ff6b83;
}

.mission-card.ready,
.mission-card.paused {
  border-top-color: #ffc861;
}

.mission-card-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 18px;
  background: linear-gradient(135deg, rgba(6, 29, 32, 0.96), rgba(11, 54, 58, 0.9));
  color: #eafffb;
}

.mission-card-head div {
  min-width: 0;
}

.mission-card-head span {
  display: block;
  color: #7bece2;
  font-size: 12px;
  font-weight: 700;
}

.mission-card-head strong {
  display: block;
  overflow: hidden;
  margin-top: 6px;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 17px;
}

.mission-card-head i {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 66px;
  height: 28px;
  border: 1px solid rgba(123, 236, 226, 0.45);
  border-radius: 999px;
  color: #7bece2;
  font-style: normal;
  font-weight: 700;
}

.mission-card-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
}

.mission-card-body div {
  min-height: 62px;
  padding: 10px;
  border: 1px solid #dce8ec;
  border-radius: 6px;
  background: #f6fafb;
}

.mission-card-body span {
  display: block;
  color: #7b929b;
  font-size: 12px;
}

.mission-card-body strong {
  display: block;
  overflow: hidden;
  margin-top: 7px;
  color: #0d1f26;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mission-card-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 14px 12px;
}

.mission-card-strip span {
  padding: 5px 8px;
  border-radius: 999px;
  background: #eef7f8;
  color: #55727c;
  font-size: 12px;
  font-weight: 700;
}

.mission-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid #e3edf0;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.full-control {
  width: 100%;
}

.dialog-block {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid #dce8ec;
  border-radius: 8px;
  background: #f8fbfc;
}

.dialog-block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.binding-row,
.parameter-row {
  display: grid;
  gap: 10px;
  align-items: center;
  margin-top: 10px;
}

.binding-row {
  grid-template-columns: 1.4fr 1fr 0.9fr auto auto;
}

.parameter-row {
  grid-template-columns: 1fr 1fr 0.5fr 1.3fr auto;
}

.empty-inline {
  padding: 12px;
  border: 1px dashed #c9dbe0;
  border-radius: 6px;
  color: #7b929b;
  text-align: center;
}

.detail-hero {
  display: grid;
  gap: 8px;
  padding: 18px;
  border-radius: 8px;
  background: #061d20;
  color: #eafffb;
}

.detail-hero span {
  color: #7bece2;
  font-weight: 700;
}

.detail-hero strong {
  font-size: 22px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

.detail-grid div,
.detail-device,
.detail-param {
  padding: 10px;
  border: 1px solid #dce8ec;
  border-radius: 6px;
  background: #f8fbfc;
}

.detail-grid dt {
  color: #7b929b;
  font-size: 12px;
}

.detail-grid dd {
  margin: 6px 0 0;
  font-weight: 700;
}

.mission-detail h3 {
  margin: 18px 0 10px;
  font-size: 16px;
}

.detail-device,
.detail-param {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.delete-mission p {
  margin: 14px 0 0;
  font-weight: 700;
}

@media (max-width: 1200px) {
  .mission-command,
  .mission-filter-panel {
    grid-template-columns: 1fr;
  }

  .mission-command {
    display: block;
  }

  .mission-command-metrics {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
    margin-top: 18px;
  }

  .mission-grid {
    grid-template-columns: repeat(2, minmax(280px, 1fr));
  }
}
</style>
