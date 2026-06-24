<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Pencil, Plus, RotateCcw, Search, Trash2 } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { createDevice, deleteDevice, updateDevice } from '@/api/device'
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { useDeviceStore } from '@/stores/device'
import type { Device, DeviceSavePayload, DeviceStatus, DeviceType } from '@/types/device'

const authStore = useAuthStore()
const deviceStore = useDeviceStore()
const formRef = ref<FormInstance>()
const dialogVisible = ref(false)
const deleteDialogVisible = ref(false)
const saving = ref(false)
const deletingId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const deleteTarget = ref<Device | null>(null)
const deleteAcknowledged = ref(false)
const deleteError = ref('')

const filters = reactive({
  keyword: '',
  type: '' as DeviceType | '',
  status: '' as DeviceStatus | '',
})

const form = reactive<DeviceSavePayload>({
  code: '',
  name: '',
  type: 'UAV',
  status: 'UNKNOWN',
  host: '',
  port: null,
  rosNamespace: '',
  description: '',
})

const rules: FormRules<DeviceSavePayload> = {
  code: [{ required: true, message: '请输入设备编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择设备类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择运行状态', trigger: 'change' }],
  port: [
    {
      validator: (_rule, value, callback) => {
        if (value === null || value === undefined || value === '') return callback()
        if (Number(value) >= 1 && Number(value) <= 65535) return callback()
        callback(new Error('端口范围应为 1-65535'))
      },
      trigger: 'blur',
    },
  ],
}

const typeOptions: Array<{ label: string; value: DeviceType }> = [
  { label: '无人机 UAV', value: 'UAV' },
  { label: '无人艇 USV', value: 'USV' },
  { label: 'ROS 节点', value: 'ROS_NODE' },
  { label: 'Unity 节点', value: 'UNITY_NODE' },
]

const statusOptions: Array<{ label: string; value: DeviceStatus }> = [
  { label: '在线', value: 'ONLINE' },
  { label: '离线', value: 'OFFLINE' },
  { label: '维护中', value: 'MAINTENANCE' },
  { label: '未知', value: 'UNKNOWN' },
]

const canManage = computed(() => authStore.user?.role === 'ADMIN')
const dialogTitle = computed(() => (editingId.value ? '编辑设备' : '新增设备'))
const deleteTitle = computed(() => (deleteTarget.value ? `删除 ${deleteTarget.value.name}` : '删除设备'))
const onlineCount = computed(() => deviceStore.records.filter((device) => device.status === 'ONLINE').length)
const missionUnitCount = computed(() => deviceStore.records.filter((device) => ['UAV', 'USV'].includes(device.type)).length)
const bridgeNodeCount = computed(() => deviceStore.records.filter((device) => ['ROS_NODE', 'UNITY_NODE'].includes(device.type)).length)

function typeLabel(type: DeviceType) {
  return typeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: DeviceStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function statusTag(status: DeviceStatus) {
  if (status === 'ONLINE') return 'success'
  if (status === 'MAINTENANCE') return 'warning'
  if (status === 'OFFLINE') return 'danger'
  return 'info'
}

function statusClass(status: DeviceStatus) {
  return status.toLowerCase()
}

function typeClass(type: DeviceType) {
  return type.toLowerCase().replace('_', '-')
}

function deviceInitial(type: DeviceType) {
  if (type === 'UAV') return 'UAV'
  if (type === 'USV') return 'USV'
  if (type === 'ROS_NODE') return 'ROS'
  if (type === 'UNITY_NODE') return '3D'
  return 'OBJ'
}

function endpoint(row: Device | Record<string, unknown>) {
  if (!row.host && !row.port) return '--'
  return `${row.host ?? ''}${row.port ? `:${row.port}` : ''}`
}

function formatTime(value: string) {
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
    code: '',
    name: '',
    type: 'UAV',
    status: 'UNKNOWN',
    host: '',
    port: null,
    rosNamespace: '',
    description: '',
  })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Device | Record<string, unknown>) {
  const device = row as Device
  editingId.value = device.id
  Object.assign(form, {
    code: device.code,
    name: device.name,
    type: device.type,
    status: device.status,
    host: device.host ?? '',
    port: device.port,
    rosNamespace: device.rosNamespace ?? '',
    description: device.description ?? '',
  })
  formRef.value?.clearValidate()
  dialogVisible.value = true
}

async function load(page = 0) {
  deviceStore.keyword = filters.keyword.trim()
  deviceStore.type = filters.type || undefined
  deviceStore.status = filters.status || undefined
  await deviceStore.refresh({ page })
}

async function resetFilters() {
  filters.keyword = ''
  filters.type = ''
  filters.status = ''
  await load(0)
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const payload = { ...form, port: form.port ? Number(form.port) : null }
    if (editingId.value) {
      await updateDevice(editingId.value, payload)
      ElMessage.success('设备已更新')
    } else {
      await createDevice(payload)
      ElMessage.success('设备已创建')
    }
    dialogVisible.value = false
    await load(deviceStore.page)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function openDelete(row: Device | Record<string, unknown>) {
  const device = row as Device
  deleteTarget.value = device
  deleteAcknowledged.value = false
  deleteError.value = ''
  deleteDialogVisible.value = true
}

function closeDeleteDialog() {
  if (deletingId.value !== null) return
  deleteDialogVisible.value = false
  deleteTarget.value = null
  deleteAcknowledged.value = false
  deleteError.value = ''
}

async function confirmDelete() {
  if (!deleteTarget.value || !deleteAcknowledged.value) return
  const device = deleteTarget.value
  deleteError.value = ''

  try {
    deletingId.value = device.id
    await deleteDevice(device.id)
    ElMessage.success('设备已删除')
    deleteDialogVisible.value = false
    deleteTarget.value = null
    deleteAcknowledged.value = false
    deleteError.value = ''
    await load(Math.max(0, deviceStore.records.length === 1 ? deviceStore.page - 1 : deviceStore.page))
  } catch (error) {
    deleteError.value = error instanceof Error ? error.message : '删除失败'
    ElMessage.error(deleteError.value)
  } finally {
    deletingId.value = null
  }
}

onMounted(() => load(0))
</script>

<template>
  <ConsoleLayout title="设备管理" eyebrow="DEVICE REGISTRY">
    <template #actions>
      <el-button v-if="canManage" type="primary" :icon="Plus" @click="openCreate">新增设备</el-button>
    </template>

    <el-alert
      v-if="deviceStore.error"
      title="设备数据加载失败"
      :description="deviceStore.error"
      type="error"
      show-icon
      :closable="false"
      class="section-alert"
    />

    <section class="device-command" aria-label="设备资产指挥台">
      <div class="device-command-hero">
        <p>ASSET REGISTRY</p>
        <h2>海空协同任务资产注册台</h2>
        <span>统一登记 UAV、USV、ROS 桥接节点与 Unity 仿真端，为任务控制、运行监控和后续启动编排提供资产底座。</span>
      </div>
      <div class="device-command-metrics">
        <div>
          <span>登记资产</span>
          <strong>{{ deviceStore.total }}</strong>
          <small>当前可管理设备</small>
        </div>
        <div>
          <span>在线节点</span>
          <strong>{{ onlineCount }}</strong>
          <small>当前页在线状态</small>
        </div>
        <div>
          <span>任务单元</span>
          <strong>{{ missionUnitCount }}</strong>
          <small>UAV / USV</small>
        </div>
        <div>
          <span>桥接链路</span>
          <strong>{{ bridgeNodeCount }}</strong>
          <small>ROS / Unity</small>
        </div>
      </div>
    </section>

    <section class="device-filter-panel" aria-label="设备筛选">
      <el-input v-model="filters.keyword" clearable placeholder="搜索编码、名称、地址" class="filter-keyword" @keyup.enter="load(0)" />
      <el-select v-model="filters.type" clearable placeholder="设备类型">
        <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="运行状态">
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button type="primary" :icon="Search" :loading="deviceStore.loading" @click="load(0)">查询</el-button>
      <el-button :icon="RotateCcw" @click="resetFilters">重置</el-button>
    </section>

    <section class="device-registry-section">
      <div class="section-heading">
        <div>
          <h2>任务设备</h2>
          <p>面向协同围捕任务的资产清单，删除仅隐藏登记项，不停止 ROS 或 Unity 进程。</p>
        </div>
        <el-tag effect="plain">共 {{ deviceStore.total }} 个</el-tag>
      </div>

      <div v-loading="deviceStore.loading" class="device-card-grid">
        <el-empty v-if="!deviceStore.loading && deviceStore.records.length === 0" description="暂无设备" />
        <template v-else>
          <article
            v-for="device in deviceStore.records"
            :key="device.id"
            class="device-card"
            :class="typeClass(device.type)"
          >
            <div class="device-card-top">
              <div class="device-type-mark" :class="typeClass(device.type)">{{ deviceInitial(device.type) }}</div>
              <div>
                <strong>{{ device.name }}</strong>
                <span>{{ device.code }}</span>
              </div>
              <i class="device-status-dot" :class="statusClass(device.status)"></i>
            </div>

            <div class="device-card-body">
              <div>
                <span>设备类型</span>
                <strong>{{ typeLabel(device.type) }}</strong>
              </div>
              <div>
                <span>运行状态</span>
                <strong>
                  <i class="device-status-pill" :class="statusClass(device.status)">
                    {{ statusLabel(device.status) }}
                  </i>
                </strong>
              </div>
              <div>
                <span>网络地址</span>
                <strong>{{ endpoint(device) }}</strong>
              </div>
              <div>
                <span>ROS 命名空间</span>
                <strong>{{ device.rosNamespace || '--' }}</strong>
              </div>
            </div>

            <div class="device-card-footer">
              <span>更新 {{ formatTime(device.updatedAt) }}</span>
              <div v-if="canManage" class="device-actions">
                <el-button link type="primary" :icon="Pencil" @click="openEdit(device)">编辑</el-button>
                <el-button
                  link
                  type="danger"
                  :icon="Trash2"
                  :loading="deletingId === device.id"
                  :disabled="deletingId !== null"
                  @click="openDelete(device)"
                >删除</el-button>
              </div>
            </div>
          </article>
        </template>
      </div>

      <div class="table-footer">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="deviceStore.total"
          :current-page="deviceStore.page + 1"
          :page-size="deviceStore.size"
          :page-sizes="[5, 10, 20, 50]"
          @current-change="(page: number) => load(page - 1)"
          @size-change="(size: number) => { deviceStore.size = size; load(0) }"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="620px" class="device-dialog" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="设备编码" prop="code"><el-input v-model="form.code" placeholder="例如 uav-01" /></el-form-item>
          <el-form-item label="设备名称" prop="name"><el-input v-model="form.name" placeholder="例如 巡检无人机" /></el-form-item>
          <el-form-item label="设备类型" prop="type"><el-select v-model="form.type"><el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="运行状态" prop="status"><el-select v-model="form.status"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="主机地址" prop="host"><el-input v-model="form.host" placeholder="例如 172.30.244.87" /></el-form-item>
          <el-form-item label="端口" prop="port"><el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" class="full-control" /></el-form-item>
        </div>
        <el-form-item label="ROS 命名空间" prop="rosNamespace"><el-input v-model="form.rosNamespace" placeholder="例如 /uav_usv/uav" /></el-form-item>
        <el-form-item label="说明" prop="description"><el-input v-model="form.description" type="textarea" :rows="3" placeholder="记录节点职责、部署位置或联调用途" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteDialogVisible"
      :title="deleteTitle"
      width="520px"
      class="device-delete-dialog"
      :close-on-click-modal="deletingId === null"
      @closed="closeDeleteDialog"
    >
      <div v-if="deleteTarget" class="delete-confirm">
        <el-alert
          v-if="deleteError"
          title="删除失败"
          :description="deleteError"
          type="error"
          show-icon
          :closable="false"
        />
        <el-alert
          title="此操作会将设备从设备管理和运行监控列表中隐藏"
          description="平台会保留历史状态事件和遥测记录，后续如需恢复可由数据库或恢复功能处理。"
          type="warning"
          show-icon
          :closable="false"
        />
        <dl class="delete-device-meta">
          <div>
            <dt>设备名称</dt>
            <dd>{{ deleteTarget.name }}</dd>
          </div>
          <div>
            <dt>设备编码</dt>
            <dd>{{ deleteTarget.code }}</dd>
          </div>
          <div>
            <dt>设备类型</dt>
            <dd>{{ typeLabel(deleteTarget.type) }}</dd>
          </div>
          <div>
            <dt>当前状态</dt>
            <dd><el-tag :type="statusTag(deleteTarget.status)" effect="plain">{{ statusLabel(deleteTarget.status) }}</el-tag></dd>
          </div>
        </dl>
        <div class="delete-impact">
          <span>删除影响</span>
          <ul>
            <li>设备不再出现在设备管理、运行监控和后续任务选择中。</li>
            <li>如果 ROS 或 Unity 仍在上报同一编码，平台不会再把它显示为可管理设备。</li>
            <li>历史运行数据不会立即清空，便于后续审计和问题追踪。</li>
          </ul>
        </div>
        <el-checkbox v-model="deleteAcknowledged">我确认隐藏该设备，并了解这不会停止 ROS 或 Unity 进程</el-checkbox>
      </div>
      <template #footer>
        <el-button :disabled="deletingId !== null" @click="closeDeleteDialog">取消</el-button>
        <el-button
          type="danger"
          :icon="Trash2"
          :loading="deletingId !== null"
          :disabled="!deleteAcknowledged || deletingId !== null"
          @click="confirmDelete"
        >
          确认删除
        </el-button>
      </template>
    </el-dialog>
  </ConsoleLayout>
</template>
