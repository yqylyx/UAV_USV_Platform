<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'

export type QuickControlDevice = {
  code: string
  name: string
  type: 'UAV' | 'USV'
  status?: string | null
}

export type VehicleQuickCommand = {
  commandType: RuntimeCommandType
  deviceCodes: string[]
  label: string
}

const props = withDefaults(
  defineProps<{
    vehicleType: 'UAV' | 'USV'
    devices: QuickControlDevice[]
    selectedDeviceCode?: string
    busy?: boolean
    feedback?: Record<string, RuntimeCommandStatus | undefined>
    compact?: boolean
  }>(),
  {
    selectedDeviceCode: '',
    busy: false,
    feedback: () => ({}),
    compact: false,
  },
)

const emit = defineEmits<{
  select: [deviceCode: string]
  command: [command: VehicleQuickCommand]
}>()

const groupMode = ref(false)

const typeDevices = computed(() => props.devices.filter((device) => device.type === props.vehicleType))
const selectedDevice = computed(
  () =>
    typeDevices.value.find((device) => normalizeCode(device.code) === normalizeCode(props.selectedDeviceCode)) ??
    typeDevices.value[0] ??
    null,
)

const actions = computed<Array<{ label: string; commandType: RuntimeCommandType; tone?: string }>>(() => {
  if (props.vehicleType === 'UAV') {
    return [
      { label: '起飞', commandType: 'UAV_TAKEOFF', tone: 'primary' },
      { label: '悬停', commandType: 'UAV_HOVER' },
      { label: '返航', commandType: 'UAV_RETURN' },
      { label: '降落', commandType: 'UAV_LAND', tone: 'warning' },
    ]
  }
  return [
    { label: '离泊启动', commandType: 'USV_DEPART', tone: 'primary' },
    { label: '定点保持', commandType: 'USV_HOLD' },
    { label: '返航', commandType: 'USV_RETURN' },
    { label: '停止推进', commandType: 'USV_STOP', tone: 'warning' },
  ]
})

const title = computed(() => (props.vehicleType === 'UAV' ? '无人机快捷控制' : '无人艇快捷控制'))
const typeLabel = computed(() => (props.vehicleType === 'UAV' ? 'UAV' : 'USV'))
const selectedFeedback = computed(() => {
  const code = selectedDevice.value?.code
  return code ? props.feedback[normalizeCode(code)] : undefined
})

watch(
  typeDevices,
  (devices) => {
    if (!devices.length || selectedDevice.value) return
    emit('select', devices[0]!.code)
  },
  { immediate: true },
)

function normalizeCode(code: string) {
  return code.trim().toLowerCase()
}

function statusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    ONLINE: '在线',
    OFFLINE: '离线',
    UNKNOWN: '等待遥测',
    MAINTENANCE: '维护中',
    PENDING: '等待下发',
    DISPATCHED: '等待确认',
    ACKNOWLEDGED: '已确认',
    FAILED: '执行失败',
    TIMEOUT: '确认超时',
  }
  return status ? labels[status] ?? status : '等待遥测'
}

function issue(commandType: RuntimeCommandType, label: string) {
  const deviceCodes = groupMode.value
    ? typeDevices.value.map((device) => device.code)
    : selectedDevice.value
      ? [selectedDevice.value.code]
      : []
  if (!deviceCodes.length || props.busy) return
  emit('command', { commandType, deviceCodes, label })
}
</script>

<template>
  <article class="vehicle-quick-control" :class="[vehicleType.toLowerCase(), { compact }]">
    <header>
      <div>
        <span>{{ typeLabel }}</span>
        <strong>{{ title }}</strong>
      </div>
      <button type="button" class="group-toggle" :class="{ active: groupMode }" @click="groupMode = !groupMode">
        {{ groupMode ? '编组控制' : '单机控制' }}
      </button>
    </header>

    <div class="device-chips">
      <button
        v-for="device in typeDevices"
        :key="device.code"
        type="button"
        :class="{ active: normalizeCode(device.code) === normalizeCode(selectedDevice?.code || '') }"
        @click="emit('select', device.code)"
      >
        {{ device.code.toUpperCase() }}
      </button>
    </div>

    <div class="selected-state">
      <span>{{ groupMode ? `${typeDevices.length} 台${vehicleType === 'UAV' ? '无人机' : '无人艇'}` : selectedDevice?.name || '未选择设备' }}</span>
      <b :class="(selectedFeedback || selectedDevice?.status || 'unknown').toLowerCase()">
        {{ statusLabel(selectedFeedback || selectedDevice?.status) }}
      </b>
    </div>

    <div class="command-grid">
      <button
        v-for="action in actions"
        :key="action.commandType"
        type="button"
        :class="action.tone"
        :disabled="busy || typeDevices.length === 0"
        @click="issue(action.commandType, action.label)"
      >
        <span>{{ action.label }}</span>
        <small>{{ groupMode ? `全部 ${typeLabel}` : selectedDevice?.code.toUpperCase() }}</small>
      </button>
    </div>
  </article>
</template>

<style scoped>
.vehicle-quick-control {
  --accent: #ffca3a;
  --accent-rgb: 255, 202, 58;
  padding: 14px;
  background: linear-gradient(145deg, rgba(7, 24, 31, 0.97), rgba(8, 18, 26, 0.94));
  border: 1px solid rgba(var(--accent-rgb), 0.46);
  border-radius: 10px;
  box-shadow: inset 0 0 28px rgba(var(--accent-rgb), 0.035);
}

.vehicle-quick-control.usv {
  --accent: #ff665e;
  --accent-rgb: 255, 102, 94;
}

header,
.selected-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

header span,
header strong {
  display: block;
}

header span {
  color: var(--accent);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.18em;
}

header strong {
  margin-top: 2px;
  color: #f2fffd;
  font-size: 15px;
}

.group-toggle,
.device-chips button,
.command-grid button {
  color: #dff8f4;
  font: inherit;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(150, 205, 203, 0.2);
  border-radius: 5px;
}

.group-toggle {
  min-height: 28px;
  padding: 0 9px;
  font-size: 10px;
  font-weight: 800;
}

.group-toggle.active,
.device-chips button.active {
  color: #071317;
  background: var(--accent);
  border-color: var(--accent);
}

.device-chips {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 12px;
}

.device-chips button {
  min-height: 31px;
  color: #b8cfcd;
  font-size: 11px;
  font-weight: 900;
}

.selected-state {
  min-height: 32px;
  margin-top: 8px;
  color: #89aaa8;
  font-size: 11px;
}

.selected-state b {
  color: #7ce5ab;
}

.selected-state b.failed,
.selected-state b.timeout,
.selected-state b.offline {
  color: #ff746f;
}

.selected-state b.dispatched,
.selected-state b.pending,
.selected-state b.unknown {
  color: #ffd76e;
}

.command-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.command-grid button {
  min-height: 52px;
  padding: 8px;
}

.command-grid button:hover:not(:disabled),
.command-grid button.primary {
  color: #061113;
  background: var(--accent);
  border-color: var(--accent);
}

.command-grid button.warning {
  border-color: rgba(255, 112, 105, 0.52);
}

.command-grid button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.command-grid span,
.command-grid small {
  display: block;
}

.command-grid span {
  font-size: 12px;
  font-weight: 900;
}

.command-grid small {
  margin-top: 3px;
  font-size: 9px;
  opacity: 0.68;
}

.compact {
  padding: 11px;
}

.compact .command-grid button {
  min-height: 44px;
}
</style>
