<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Eye, Pencil, Plus, RotateCcw, Search, Trash2 } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'

import { createMission, deleteMission, executeMissionAction, fetchMission, updateMission } from '@/api/mission'
import type { MissionAction } from '@/api/mission'
import { fetchDevices } from '@/api/device'
import { fetchRuntimeCommandLogs, issueRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandResult, RuntimeCommandStatus } from '@/api/runtimeControl'
import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import MissionGroupControl from '@/components/control/MissionGroupControl.vue'
import VehicleQuickControl from '@/components/control/VehicleQuickControl.vue'
import VehicleGlyph from '@/components/control/VehicleGlyph.vue'
import type { VehicleQuickCommand } from '@/components/control/VehicleQuickControl.vue'
import MissionTrajectoryMap from '@/components/mission/MissionTrajectoryMap.vue'
import { useAuthStore } from '@/stores/auth'
import { useMissionStore } from '@/stores/mission'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import type { Device } from '@/types/device'
import { normalizeOperationalState } from '@/utils/runtimeOperationalState'
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
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
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
const trajectoryMap = ref<InstanceType<typeof MissionTrajectoryMap> | null>(null)
const selectedDeviceCode = ref('uav-02')
const selectedMissionId = ref<number | null>(null)
const vehicleCommandBusy = ref(false)
const commandFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
const operationalStates = ref<Record<string, string | undefined>>({})

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
const currentMission = computed(
  () =>
    missionStore.records.find((item) => item.id === selectedMissionId.value) ??
    missionStore.records.find((item) => item.status === 'RUNNING') ??
    missionStore.records[0] ??
    null,
)
const controlDevices = computed(() => {
  const missionDetail = detail.value
  if (missionDetail && missionDetail.mission.id === currentMission.value?.id) {
    return missionDetail.devices
      .filter((binding) => binding.type === 'UAV' || binding.type === 'USV')
      .map((binding) => {
        const device = deviceOptions.value.find((item) => item.id === binding.deviceId)
        return {
          code: binding.code ?? device?.code ?? '',
          name: binding.name ?? device?.name ?? binding.code ?? '未知载具',
          type: binding.type as 'UAV' | 'USV',
          status: binding.status ?? device?.status ?? 'UNKNOWN',
        }
      })
      .filter((device) => device.code)
  }
  return deviceOptions.value
    .filter((device) => device.type === 'UAV' || device.type === 'USV')
    .map((device) => ({
      code: device.code,
      name: device.name,
      type: device.type as 'UAV' | 'USV',
      status: device.status,
    }))
    .filter((device) => device.code)
})
const activeRunId = computed(() => {
  const missionDetail = detail.value
  if (!missionDetail || missionDetail.mission.id !== currentMission.value?.id) return undefined
  return missionDetail.currentRun?.id
})
const requiredDeviceCodes = computed(() => {
  const missionDetail = detail.value
  if (missionDetail && missionDetail.mission.id === currentMission.value?.id) {
    return missionDetail.devices
      .filter((binding) => binding.required && (binding.type === 'UAV' || binding.type === 'USV') && binding.code)
      .map((binding) => normalizeDeviceCode(binding.code!))
  }
  return controlDevices.value.map((device) => normalizeDeviceCode(device.code))
})
const fleetReady = computed(() =>
  requiredDeviceCodes.value.length > 0 &&
  requiredDeviceCodes.value.every((code) =>
    ['AIRBORNE', 'SAILING', 'HOLDING'].includes(
      normalizeOperationalState(operationalStates.value[code], code.startsWith('uav') ? 'UAV' : 'USV'),
    ),
  ),
)
const readinessText = computed(() => {
  const ready = requiredDeviceCodes.value.filter((code) =>
    ['AIRBORNE', 'SAILING', 'HOLDING'].includes(
      normalizeOperationalState(operationalStates.value[code], code.startsWith('uav') ? 'UAV' : 'USV'),
    ),
  ).length
  return `${ready}/${requiredDeviceCodes.value.length} 必要载具就绪`
})
const selectedControlDevice = computed(
  () => controlDevices.value.find((device) => normalizeDeviceCode(device.code) === normalizeDeviceCode(selectedDeviceCode.value)) ?? controlDevices.value[0] ?? null,
)
const selectedOperationalLabel = computed(() => {
  const code = normalizeDeviceCode(selectedControlDevice.value?.code ?? '')
  const state = normalizeOperationalState(operationalStates.value[code], selectedControlDevice.value?.type)
  const labels: Record<string, string> = {
    GROUNDED: '地面待命', AIRBORNE: '空中执行', HOLDING: '安全保持', RETURNING: '返航中', LANDING: '降落中',
    MOORED: '靠泊待命', SAILING: '航行中', STOPPED: '已停止', ERROR: '异常',
  }
  return labels[state] ?? '等待状态'
})
const commandFeedbackRows = computed(() =>
  controlDevices.value
    .map((device) => ({
      code: normalizeDeviceCode(device.code),
      type: device.type,
      status: commandFeedback.value[normalizeDeviceCode(device.code)],
      state: operationalStates.value[normalizeDeviceCode(device.code)],
    }))
    .filter((item) => item.status)
    .slice(0, 5),
)
const missionProgress = computed(() => {
  const stage = currentMission.value?.stage
  const progress: Partial<Record<MissionStage, number>> = {
    PREPARE: 8,
    TARGET_DETECTED: 24,
    ASSIGNMENT: 38,
    TRACKING: 56,
    ENCIRCLEMENT: 72,
    CAPTURED: 92,
    EVALUATION: 100,
  }
  return stage ? progress[stage] ?? 0 : 0
})
const encirclementCount = computed(
  () => missionStore.records.filter((item) => item.type === 'COOPERATIVE_ENCIRCLEMENT').length,
)

function typeLabel(type: MissionType) {
  return typeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: MissionStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function commandStatusLabel(status?: RuntimeCommandStatus) {
  const labels: Partial<Record<RuntimeCommandStatus, string>> = {
    PENDING: '等待下发', DISPATCHED: '等待确认', ACKNOWLEDGED: '已确认', FAILED: '执行失败', TIMEOUT: '确认超时',
  }
  return status ? labels[status] ?? status : '无指令'
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
  if (!selectedMissionId.value || !missionStore.records.some((item) => item.id === selectedMissionId.value)) {
    selectedMissionId.value = missionStore.records.find((item) => item.status === 'RUNNING')?.id ?? missionStore.records[0]?.id ?? null
  }
  const mission = currentMission.value
  if (mission) {
    detail.value = await fetchMission(mission.id).catch(() => detail.value)
    initializeOperationalStates(mission)
  }
}

function missionRowClass({ row }: { row: Mission }) {
  return row.id === selectedMissionId.value ? 'mission-row-selected' : ''
}

async function selectMission(row: Mission | Record<string, unknown>) {
  const mission = row as Mission
  const changed = selectedMissionId.value !== mission.id
  selectedMissionId.value = mission.id
  if (changed) commandFeedback.value = {}
  detailLoading.value = true
  try {
    detail.value = await fetchMission(mission.id)
    initializeOperationalStates(mission, changed)
    if (!controlDevices.value.some((device) => normalizeDeviceCode(device.code) === normalizeDeviceCode(selectedDeviceCode.value))) {
      selectedDeviceCode.value = controlDevices.value[0]?.code ?? ''
    }
  } finally {
    detailLoading.value = false
  }
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
  selectedMissionId.value = mission.id
  if (deviceOptions.value.length === 0) await loadDevices()
  detailLoading.value = true
  try {
    const result = await fetchMission(mission.id)
    detail.value = result
    initializeOperationalStates(mission, true)
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
  selectedMissionId.value = mission.id
  detailLoading.value = true
  detailVisible.value = true
  try {
    detail.value = await fetchMission(mission.id)
    initializeOperationalStates(mission)
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
    if (result.command && (result.command.status === 'DISPATCHED' || result.command.status === 'PENDING')) {
      unityBridgeStore.sendControlCommand(missionUnityCommand(action), '', result.command.commandKey)
    }
    const latest = result.detail
    detail.value = detail.value?.mission.id === mission.id ? latest : detail.value
    if (result.command?.status === 'DISPATCHED' || result.command?.status === 'PENDING') {
      ElMessage.warning(`${latest.mission.name}：指令已下发，等待外部组件确认`)
      void monitorMissionActionAcknowledgement(result.command.commandKey)
    } else if (result.command?.status === 'FAILED' || result.command?.status === 'TIMEOUT') {
      ElMessage.error(`${latest.mission.name}：${result.command.detail || '控制指令执行失败'}`)
    } else {
      ElMessage.success(`${latest.mission.name}：${statusLabel(latest.mission.status)}`)
    }
    await load(missionStore.page)
    return latest
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

async function monitorMissionActionAcknowledgement(commandKey: string) {
  for (let attempt = 0; attempt < 18; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
    const logs = await fetchRuntimeCommandLogs().catch(() => [])
    const command = logs.find((item) => item.commandKey === commandKey)
    if (!command || command.status === 'PENDING' || command.status === 'DISPATCHED') continue
    await load(missionStore.page)
    if (command.status === 'ACKNOWLEDGED') ElMessage.success('Unity 已确认任务状态变更')
    else ElMessage.error(command.detail || 'Unity 未能确认任务状态变更')
    return
  }
}

function missionUnityCommand(action: MissionAction) {
  return {
    start: 'missionStart',
    pause: 'missionPause',
    resume: 'missionResume',
    complete: 'missionComplete',
    fail: 'missionFail',
    cancel: 'missionCancel',
    ready: 'missionResume',
  }[action]
}

function normalizeDeviceCode(code: string) {
  return code.trim().toLowerCase()
}

function initializeOperationalStates(mission: Mission, force = false) {
  const next = { ...operationalStates.value }
  for (const device of controlDevices.value) {
    const code = normalizeDeviceCode(device.code)
    if (!force && mission.status === 'READY' && next[code]) continue
    if (device.type === 'UAV') {
      next[code] = mission.status === 'RUNNING' ? 'AIRBORNE' : mission.status === 'PAUSED' ? 'HOLDING' : 'GROUNDED'
    } else {
      next[code] = mission.status === 'RUNNING' ? 'SAILING' : mission.status === 'PAUSED' ? 'HOLDING' : 'MOORED'
    }
  }
  operationalStates.value = next
}

function operationalStateAfterCommand(commandType: VehicleQuickCommand['commandType']) {
  const states: Partial<Record<VehicleQuickCommand['commandType'], string>> = {
    UAV_TAKEOFF: 'AIRBORNE',
    UAV_HOVER: 'HOLDING',
    UAV_RESUME: 'AIRBORNE',
    UAV_RETURN: 'RETURNING',
    UAV_LAND: 'LANDING',
    UAV_EMERGENCY_LAND: 'LANDING',
    USV_DEPART: 'SAILING',
    USV_HOLD: 'HOLDING',
    USV_RESUME: 'SAILING',
    USV_RETURN: 'RETURNING',
    USV_STOP: 'STOPPED',
    USV_EMERGENCY_STOP: 'STOPPED',
  }
  return states[commandType]
}

function unityBridgeCommand(commandType: VehicleQuickCommand['commandType']) {
  const commands: Partial<Record<VehicleQuickCommand['commandType'], string>> = {
    UAV_TAKEOFF: 'uavTakeoff',
    UAV_HOVER: 'uavHover',
    UAV_RESUME: 'uavResume',
    UAV_RETURN: 'uavReturn',
    UAV_LAND: 'uavLand',
    UAV_EMERGENCY_LAND: 'uavEmergencyLand',
    USV_DEPART: 'usvDepart',
    USV_HOLD: 'usvHold',
    USV_RESUME: 'usvResume',
    USV_RETURN: 'usvReturn',
    USV_STOP: 'usvStop',
    USV_EMERGENCY_STOP: 'usvEmergencyStop',
  }
  return commands[commandType] ?? commandType.toLowerCase()
}

function handleTrajectoryDeviceStateChange(deviceCode: string, state: string) {
  operationalStates.value = { ...operationalStates.value, [normalizeDeviceCode(deviceCode)]: state }
}

async function monitorCommandAcknowledgement(
  result: RuntimeCommandResult,
  deviceCode: string,
  commandType: VehicleQuickCommand['commandType'],
) {
  if (result.status !== 'PENDING' && result.status !== 'DISPATCHED') return
  for (let attempt = 0; attempt < 18; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
    const logs = await fetchRuntimeCommandLogs().catch(() => [])
    const command = logs.find((item) => item.commandKey === result.commandKey)
    if (!command || command.status === 'PENDING' || command.status === 'DISPATCHED') continue
    commandFeedback.value = { ...commandFeedback.value, [deviceCode]: command.status }
    if (command.status === 'ACKNOWLEDGED') {
      const nextState = operationalStateAfterCommand(commandType)
      if (nextState) operationalStates.value = { ...operationalStates.value, [deviceCode]: nextState }
    }
    trajectoryMap.value?.applyVehicleCommand(commandType, [deviceCode], [command.status])
    return
  }
}

async function restoreOperationalStatesFromCommands() {
  const logs = await fetchRuntimeCommandLogs().catch(() => [])
  const restored = new Set<string>()
  for (const command of logs) {
    if (command.status !== 'ACKNOWLEDGED' || command.deviceId == null) continue
    const device = deviceOptions.value.find((item) => item.id === command.deviceId)
    if (!device || (device.type !== 'UAV' && device.type !== 'USV')) continue
    const code = normalizeDeviceCode(device.code)
    if (restored.has(code)) continue
    const state = operationalStateAfterCommand(command.commandType)
    if (!state) continue
    restored.add(code)
    operationalStates.value = { ...operationalStates.value, [code]: state }
    commandFeedback.value = { ...commandFeedback.value, [code]: command.status }
    trajectoryMap.value?.applyVehicleCommand(command.commandType, [code], [command.status])
  }
}

type VehicleBatchResult = {
  total: number
  acknowledged: number
  waiting: number
  failed: number
  allAcknowledged: boolean
}

async function sendVehicleCommand(
  command: VehicleQuickCommand,
  options: { manageBusy?: boolean; notify?: boolean } = {},
): Promise<VehicleBatchResult> {
  const manageBusy = options.manageBusy ?? true
  const notify = options.notify ?? true
  if (manageBusy) vehicleCommandBusy.value = true
  const statuses = await Promise.all(
    command.deviceCodes.map(async (deviceCode): Promise<RuntimeCommandStatus> => {
      const normalizedCode = normalizeDeviceCode(deviceCode)
      commandFeedback.value = { ...commandFeedback.value, [normalizedCode]: 'PENDING' }
      try {
        const result = await issueRuntimeCommand({
          commandType: command.commandType,
          runId: activeRunId.value,
          deviceCode: normalizedCode,
          detail: `任务控制 / ${command.label}`,
          payload: JSON.stringify({ source: 'mission-trajectory-map' }),
        })
        unityBridgeStore.sendControlCommand(unityBridgeCommand(command.commandType), normalizedCode, result.commandKey)
        commandFeedback.value = { ...commandFeedback.value, [normalizedCode]: result.status }
        if (result.status === 'ACKNOWLEDGED') {
          const nextState = operationalStateAfterCommand(command.commandType)
          if (nextState) operationalStates.value = { ...operationalStates.value, [normalizedCode]: nextState }
        }
        void monitorCommandAcknowledgement(result, normalizedCode, command.commandType)
        return result.status
      } catch (error) {
        commandFeedback.value = { ...commandFeedback.value, [normalizedCode]: 'FAILED' }
        return 'FAILED'
      }
    }),
  )
  trajectoryMap.value?.applyVehicleCommand(command.commandType, command.deviceCodes, statuses)
  const result = {
    total: statuses.length,
    acknowledged: statuses.filter((status) => status === 'ACKNOWLEDGED').length,
    waiting: statuses.filter((status) => status === 'PENDING' || status === 'DISPATCHED').length,
    failed: statuses.filter((status) => status === 'FAILED' || status === 'TIMEOUT').length,
    allAcknowledged: statuses.length === 0 || statuses.every((status) => status === 'ACKNOWLEDGED'),
  }
  if (notify) {
    if (result.allAcknowledged) ElMessage.success(`${command.label}：${result.acknowledged}/${result.total} 台已确认`)
    else if (result.failed > 0) ElMessage.error(`${command.label}：成功 ${result.acknowledged}，等待 ${result.waiting}，失败 ${result.failed}`)
    else ElMessage.warning(`${command.label}：${result.waiting} 台等待外部组件确认`)
  }
  if (manageBusy) vehicleCommandBusy.value = false
  return result
}

async function sendFleetCommand(
  vehicleType: 'UAV' | 'USV',
  commandType: VehicleQuickCommand['commandType'],
  label: string,
  options: { manageBusy?: boolean; notify?: boolean } = {},
) {
  const allowedStates: Partial<Record<VehicleQuickCommand['commandType'], string[]>> = {
    UAV_TAKEOFF: ['GROUNDED'],
    UAV_HOVER: ['AIRBORNE', 'RETURNING'],
    UAV_RESUME: ['HOLDING'],
    UAV_RETURN: ['AIRBORNE', 'HOLDING'],
    UAV_LAND: ['AIRBORNE', 'HOLDING', 'RETURNING'],
    USV_DEPART: ['MOORED', 'STOPPED'],
    USV_HOLD: ['SAILING', 'RETURNING'],
    USV_RESUME: ['HOLDING'],
    USV_RETURN: ['SAILING', 'HOLDING'],
    USV_STOP: ['SAILING', 'HOLDING', 'RETURNING'],
  }
  const states = allowedStates[commandType]
  const deviceCodes = controlDevices.value
    .filter((device) => device.type === vehicleType)
    .filter((device) =>
      !states ||
      states.includes(
        normalizeOperationalState(operationalStates.value[normalizeDeviceCode(device.code)], device.type),
      ),
    )
    .map((device) => device.code)
  return sendVehicleCommand({ commandType, deviceCodes, label }, options)
}

async function sendFleetPair(
  uavCommand: VehicleQuickCommand['commandType'],
  uavLabel: string,
  usvCommand: VehicleQuickCommand['commandType'],
  usvLabel: string,
) {
  vehicleCommandBusy.value = true
  try {
    const [uav, usv] = await Promise.all([
      sendFleetCommand('UAV', uavCommand, uavLabel, { manageBusy: false, notify: false }),
      sendFleetCommand('USV', usvCommand, usvLabel, { manageBusy: false, notify: false }),
    ])
    const result: VehicleBatchResult = {
      total: uav.total + usv.total,
      acknowledged: uav.acknowledged + usv.acknowledged,
      waiting: uav.waiting + usv.waiting,
      failed: uav.failed + usv.failed,
      allAcknowledged: uav.allAcknowledged && usv.allAcknowledged,
    }
    if (result.allAcknowledged) ElMessage.success(`编组指令完成：${result.acknowledged}/${result.total} 台已确认`)
    else if (result.failed > 0) ElMessage.error(`编组部分执行：成功 ${result.acknowledged}，等待 ${result.waiting}，失败 ${result.failed}`)
    else ElMessage.warning(`编组指令等待确认：${result.waiting}/${result.total} 台`)
    return result
  } finally {
    vehicleCommandBusy.value = false
  }
}

async function handleMissionGroupAction(action: 'deploy' | 'start' | 'pause' | 'resume' | 'return' | 'abort') {
  let mission = currentMission.value
  if (!mission) {
    ElMessage.warning('请先创建或选择任务')
    return
  }
  if (action === 'deploy') {
    if (mission.status === 'DRAFT') {
      const ready = await runMissionAction(mission, 'ready')
      if (!ready) return
      mission = ready.mission
    }
    const deployed = await sendFleetPair('UAV_TAKEOFF', '无人机编组起飞', 'USV_DEPART', '无人艇编组离泊')
    if (deployed.allAcknowledged) trajectoryMap.value?.applyMissionAction('deploy')
    return
  }
  if (action === 'return') {
    try {
      await ElMessageBox.confirm('将向全部 UAV/USV 下发返航，并在确认后取消当前任务。是否继续？', '全体返航', {
        confirmButtonText: '确认返航',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
    const returning = await sendFleetPair('UAV_RETURN', '无人机编组返航', 'USV_RETURN', '无人艇编组返航')
    if (!returning.allAcknowledged) return
    await runMissionAction(mission, 'cancel')
    operationalStates.value = Object.fromEntries(
      controlDevices.value.map((device) => [normalizeDeviceCode(device.code), 'RETURNING']),
    )
    trajectoryMap.value?.applyMissionAction('return')
    return
  }
  if (action === 'pause') {
    const held = await sendFleetPair('UAV_HOVER', '无人机编组悬停', 'USV_HOLD', '无人艇编组定点保持')
    if (!held.allAcknowledged) return
    await runMissionAction(mission, 'pause')
    trajectoryMap.value?.applyMissionAction('pause')
    return
  }
  if (action === 'resume') {
    const resumed = await sendFleetPair('UAV_RESUME', '无人机继续任务', 'USV_RESUME', '无人艇继续航行')
    if (!resumed.allAcknowledged) return
    await runMissionAction(mission, 'resume')
    trajectoryMap.value?.applyMissionAction('resume')
    return
  }
  if (action === 'abort') {
    try {
      await ElMessageBox.confirm('终止后任务将标记异常；系统仍会分别记录未能安全保持的设备。是否继续？', '终止任务', {
        confirmButtonText: '确认终止',
        cancelButtonText: '取消',
        type: 'error',
      })
    } catch {
      return
    }
    await sendFleetPair('UAV_HOVER', '无人机安全悬停', 'USV_HOLD', '无人艇安全保持')
    await runMissionAction(mission, 'fail')
    trajectoryMap.value?.applyMissionAction('abort')
    return
  }
  if (!fleetReady.value) {
    ElMessage.warning(`编组尚未就绪：${readinessText.value}`)
    return
  }
  const started = await runMissionAction(mission, 'start')
  if (started?.mission.status === 'RUNNING') trajectoryMap.value?.applyMissionAction('start')
}

async function handleTableMissionAction(row: Mission | Record<string, unknown>, action: MissionAction) {
  const mission = row as Mission
  await selectMission(mission)
  if (action === 'ready') {
    await runMissionAction(mission, 'ready')
    return
  }
  if (action === 'start') return handleMissionGroupAction('start')
  if (action === 'pause') return handleMissionGroupAction('pause')
  if (action === 'resume') return handleMissionGroupAction('resume')
  if (action === 'fail') return handleMissionGroupAction('abort')
  if (action === 'cancel') {
    if (mission.status === 'DRAFT' || mission.status === 'READY') await runMissionAction(mission, 'cancel')
    else await handleMissionGroupAction('return')
    return
  }
  if (action === 'complete') {
    const held = await sendFleetPair('UAV_HOVER', '无人机任务完成悬停', 'USV_HOLD', '无人艇任务完成保持')
    if (!held.allAcknowledged) return
    await runMissionAction(mission, 'complete')
    trajectoryMap.value?.applyMissionAction('pause')
  }
}

onMounted(async () => {
  await Promise.all([load(0), loadDevices()])
  await restoreOperationalStatesFromCommands()
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

    <header class="mission-hf-statusbar">
      <div>
        <span>当前任务</span>
        <strong>{{ currentMission?.code || '未选择任务' }}</strong>
        <small>{{ currentMission?.name || '请选择或创建任务方案' }}</small>
      </div>
      <div class="mission-hf-status">
        <b :class="statusClass(currentMission?.status || 'DRAFT')"><i></i>{{ currentMission ? statusLabel(currentMission.status) : '待配置' }}</b>
        <span>{{ stageLabel(currentMission?.stage || 'PREPARE') }}</span>
        <span>{{ readinessText }}</span>
      </div>
    </header>

    <section class="mission-command-layout mission-hf-layout">
      <article class="console-panel mission-map-panel">
        <div class="panel-heading">
          <div>
            <h2>协同围捕轨迹地图</h2>
            <p>按 Unity 场景的 X/Z 坐标与三角合围逻辑，在 Vue 中独立绘制定位轨迹。</p>
          </div>
          <div class="mission-map-actions">
            <el-tag type="success" effect="plain">VUE SIMULATION</el-tag>
            <el-button v-if="currentMission" @click="openEdit(currentMission)">编辑当前方案</el-button>
            <el-button v-else @click="openCreate">新建方案</el-button>
          </div>
        </div>
        <MissionTrajectoryMap
          ref="trajectoryMap"
          :mission-name="currentMission?.name || '三机三艇协同围捕预演'"
          :mission-status="currentMission?.status || 'READY'"
          :selected-device-code="selectedDeviceCode"
          :command-feedback="commandFeedback"
          :trajectory-frame="trajectoryStore.frame"
          @select-device="selectedDeviceCode = $event"
          @device-state-change="handleTrajectoryDeviceStateChange"
        />
      </article>

      <aside class="mission-side-stack">
        <article class="mission-current-device-card">
          <header>
            <VehicleGlyph v-if="selectedControlDevice" :type="selectedControlDevice.type" size="medium" active />
            <div class="mission-current-device-identity">
              <span>当前设备控制</span>
              <strong>{{ selectedControlDevice?.code.toUpperCase() || '--' }}</strong>
            </div>
            <b>{{ selectedOperationalLabel }}</b>
          </header>
          <div class="mission-device-telemetry">
            <div><span>设备类型</span><strong>{{ selectedControlDevice?.type || '--' }}</strong></div>
            <div><span>链路状态</span><strong>{{ selectedControlDevice?.status || '--' }}</strong></div>
            <div><span>任务角色</span><strong>{{ selectedControlDevice?.type === 'UAV' ? '空中补盲' : '海面封控' }}</strong></div>
          </div>
        </article>
        <VehicleQuickControl
          vehicle-type="UAV"
          :devices="controlDevices"
          :selected-device-code="selectedDeviceCode"
          :feedback="commandFeedback"
          :operational-states="operationalStates"
          :busy="vehicleCommandBusy"
          compact
          @select="selectedDeviceCode = $event"
          @command="sendVehicleCommand"
        />
        <VehicleQuickControl
          vehicle-type="USV"
          :devices="controlDevices"
          :selected-device-code="selectedDeviceCode"
          :feedback="commandFeedback"
          :operational-states="operationalStates"
          :busy="vehicleCommandBusy"
          compact
          @select="selectedDeviceCode = $event"
          @command="sendVehicleCommand"
        />
        <MissionGroupControl
          :mission-name="currentMission?.name || '三机三艇协同围捕'"
          :status="currentMission?.status || 'READY'"
          :busy="vehicleCommandBusy || actionLoadingId !== null"
          :progress="missionProgress"
          :can-deploy="(currentMission?.status === 'DRAFT' || currentMission?.status === 'READY') && !fleetReady"
          :can-start="fleetReady"
          :readiness-text="readinessText"
          @action="handleMissionGroupAction"
        />
        <article class="mission-command-feedback-card">
          <header>
            <div><span>COMMAND FEEDBACK</span><strong>指令反馈</strong></div>
            <b>{{ commandFeedbackRows.length }}</b>
          </header>
          <div v-if="commandFeedbackRows.length" class="mission-command-feedback-list">
            <div v-for="item in commandFeedbackRows" :key="item.code">
              <span :class="item.type.toLowerCase()">{{ item.code.toUpperCase() }}</span>
              <strong>{{ item.state || '等待状态' }}</strong>
              <b :class="item.status?.toLowerCase()">{{ commandStatusLabel(item.status) }}</b>
            </div>
          </div>
          <p v-else>暂无设备控制指令</p>
        </article>
      </aside>
    </section>

    <details class="mission-plan-manager">
      <summary>
        <span>任务方案与历史记录</span>
        <b>{{ missionStore.total }} 个任务 · 运行中 {{ runningCount }}</b>
      </summary>
      <div class="mission-plan-manager-body">
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

      <el-table
        v-loading="missionStore.loading || detailLoading"
        :data="missionStore.records"
        :row-class-name="missionRowClass"
        class="console-table"
        @row-click="selectMission"
      >
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
            <el-button link type="primary" :icon="Eye" @click.stop="openDetail(row)">详情</el-button>
            <template v-if="canManage">
              <el-button
                link
                v-for="item in missionActions(row.status)"
                :key="item.action"
                :type="item.type"
                :loading="actionLoadingId === row.id"
                @click.stop="handleTableMissionAction(row, item.action)"
              >
                {{ item.label }}
              </el-button>
              <el-button link type="primary" :icon="Pencil" @click.stop="openEdit(row)">编辑</el-button>
              <el-button link type="danger" :icon="Trash2" :loading="deletingId === row.id" @click.stop="openDelete(row)">删除</el-button>
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

      </div>
    </details>

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
