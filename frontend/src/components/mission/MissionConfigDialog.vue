<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { CheckCircle2, Cpu, Plane, Route, Shield, Ship, Target } from '@lucide/vue'
import type { Device } from '@/types/device'
import type { AlgorithmDefinition, MissionDetail, MissionDeviceRole, MissionSavePayload, MissionStatus, MissionType } from '@/types/mission'

const props = defineProps<{
  modelValue: boolean
  detail: MissionDetail | null
  devices: Device[]
  algorithms: AlgorithmDefinition[]
  readonly?: boolean
  saving?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; save: [payload: MissionSavePayload] }>()

const form = reactive({
  code: '', name: '', algorithmCode: 'GB_SFLA_CS', targetName: '海面机动目标', escortTargetName: '护航目标-01',
  missionArea: '灯塔海域', targetBehavior: 'MOVING', routePreset: 'LIGHTHOUSE_SAFE_ROUTE', escortSpeed: 'LOW',
  threatDirection: 'front_right', threatMode: 'AUTO', description: '',
})

const fallbackAlgorithms: AlgorithmDefinition[] = [
  { id: -1, code: 'GB_SFLA_CS', name: 'GB-SFLA-CS 协同围捕', version: '1.0.0', missionType: 'COOPERATIVE_ENCIRCLEMENT', adapterType: 'PYTHON_PROCESS', deviceScale: '3 UAV + 3 USV + 1 目标', enabled: true, defaultForType: true, description: '粒球、SFLA 与 CS 混合围捕算法。' },
  { id: -2, code: 'ESCORT_GUARD', name: '混合 UAV/USV 护航守卫', version: '1.0.0', missionType: 'COOPERATIVE_ESCORT', adapterType: 'PYTHON_PROCESS', deviceScale: '3 UAV + 3 USV + 护航目标 + 威胁目标', enabled: true, defaultForType: true, description: '移动护航目标与动态威胁阻断算法。' },
]
const enabledAlgorithms = computed(() => (props.algorithms.length ? props.algorithms : fallbackAlgorithms).filter(item => item.enabled))
const selectedAlgorithm = computed(() => enabledAlgorithms.value.find(item => item.code === form.algorithmCode) ?? enabledAlgorithms.value[0])
const escortMode = computed(() => selectedAlgorithm.value?.missionType === 'COOPERATIVE_ESCORT')

watch(() => [props.modelValue, props.detail, props.algorithms] as const, () => {
  if (!props.modelValue) return
  const mission = props.detail?.mission
  const parameters = Object.fromEntries((props.detail?.parameters ?? []).map(item => [item.key, item.value ?? '']))
  const algorithmCode = mission?.algorithmCode || enabledAlgorithms.value.find(item => item.defaultForType)?.code || 'GB_SFLA_CS'
  Object.assign(form, {
    code: mission?.code || `EXP-${Date.now()}`,
    name: mission?.name || (algorithmCode === 'ESCORT_GUARD' ? '三机三艇协同护航演示任务' : '三机三艇协同围捕演示任务'),
    algorithmCode,
    targetName: mission?.targetName || '海面机动目标',
    escortTargetName: parameters.escort_target_name || '护航目标-01',
    missionArea: mission?.missionArea || '灯塔海域',
    targetBehavior: mission?.targetBehavior === '静止目标' ? 'STATIC' : 'MOVING',
    routePreset: parameters.route_preset || 'LIGHTHOUSE_SAFE_ROUTE',
    escortSpeed: parameters.escort_speed || 'LOW',
    threatDirection: parameters.threat_direction || 'front_right',
    threatMode: parameters.threat_mode || 'AUTO',
    description: mission?.description || (algorithmCode === 'ESCORT_GUARD' ? '三机三艇保护移动护航目标，并根据威胁方向动态部署守卫。' : '三机三艇执行 GB-SFLA-CS 协同围捕，2D 与 3D 使用同一算法帧。'),
  })
}, { immediate: true })

watch(() => form.algorithmCode, (code, previous) => {
  if (!previous || props.readonly) return
  if (code === 'ESCORT_GUARD') {
    form.name = '三机三艇协同护航演示任务'
    form.description = '三机三艇保护移动护航目标，并根据威胁方向动态部署守卫。'
  } else {
    form.name = '三机三艇协同围捕演示任务'
    form.description = '三机三艇执行协同围捕，2D 轨迹与任务中心 Unity 使用同一算法帧。'
  }
})

const fleet = computed(() => props.devices.filter(device => device.type === 'UAV' || device.type === 'USV').sort((a, b) => a.code.localeCompare(b.code)))
const selectedFleet = computed(() => [
  ...fleet.value.filter(device => device.type === 'UAV').slice(0, 3),
  ...fleet.value.filter(device => device.type === 'USV').slice(0, 3),
])
const uavCount = computed(() => selectedFleet.value.filter(device => device.type === 'UAV').length)
const usvCount = computed(() => selectedFleet.value.filter(device => device.type === 'USV').length)
const fleetReady = computed(() => uavCount.value === 3 && usvCount.value === 3)

function roleFor(device: Device, index: number): MissionDeviceRole {
  if (escortMode.value) return index === 0 ? 'LEADER' : device.type === 'UAV' ? 'UAV_TRACK' : 'USV_BLOCKADE'
  return device.type === 'UAV' ? (index === 0 ? 'UAV_RECON' : 'UAV_TRACK') : (index === 0 ? 'USV_INTERCEPT' : 'USV_BLOCKADE')
}

function buildPayload(status: MissionStatus): MissionSavePayload {
  const algorithm = selectedAlgorithm.value ?? fallbackAlgorithms[0]!
  const type = algorithm.missionType as MissionType
  const parameters = escortMode.value ? [
    { key: 'escort_target_name', value: form.escortTargetName, unit: '', description: '被保护的移动护航目标' },
    { key: 'route_preset', value: form.routePreset, unit: '', description: '护航目标安全航线' },
    { key: 'escort_speed', value: form.escortSpeed, unit: '', description: '护航目标航行速度' },
    { key: 'threat_direction', value: form.threatDirection, unit: '', description: '威胁初始方向' },
    { key: 'threat_mode', value: form.threatMode, unit: '', description: '威胁出现方式' },
  ] : [
    { key: 'target_behavior', value: form.targetBehavior, unit: '', description: '被围捕目标运动方式' },
    { key: 'minimum_capture_agents', value: '6', unit: '台', description: '完成围捕所需载具数' },
  ]
  return {
    code: form.code, name: form.name, type, executionMode: 'UNITY_STANDALONE', algorithmCode: algorithm.code,
    algorithmVersion: algorithm.version, status, stage: 'PREPARE', priority: 1,
    targetName: escortMode.value ? form.escortTargetName : form.targetName,
    targetBehavior: escortMode.value ? '沿预设航线低速航行' : form.targetBehavior === 'STATIC' ? '静止目标' : '低速机动',
    missionArea: form.missionArea, plannedStartAt: null, plannedEndAt: null, description: form.description,
    devices: selectedFleet.value.map(device => {
      const sameType = selectedFleet.value.filter(item => item.type === device.type)
      return { deviceId: device.id, role: roleFor(device, sameType.findIndex(item => item.id === device.id)), callSign: device.code, required: true, notes: `${algorithm.name} 固定三机三艇映射` }
    }),
    parameters,
  }
}
</script>

<template>
  <el-dialog :model-value="modelValue" title="实验任务配置" width="860px" top="5vh" class="mission-config-dialog" @update:model-value="emit('update:modelValue', $event)">
    <div class="config-intro"><span><Cpu :size="16"/> ALGORITHM TASK CONFIG</span><h3>{{ escortMode ? '三机三艇协同护航任务' : '三机三艇协同围捕任务' }}</h3><p>任务固定映射 UAV-01~03 与 USV-01~03；算法切换会同步更新目标类型和执行场景。</p></div>
    <el-form label-position="top" class="config-form">
      <el-form-item label="算法选择" class="wide"><el-select v-model="form.algorithmCode" :disabled="readonly"><el-option v-for="algorithm in enabledAlgorithms" :key="algorithm.code" :label="`${algorithm.name} · v${algorithm.version}`" :value="algorithm.code"><span>{{ algorithm.name }}</span><small>{{ algorithm.deviceScale }}</small></el-option></el-select></el-form-item>
      <el-form-item label="任务编号"><el-input v-model="form.code" :disabled="readonly"/></el-form-item>
      <el-form-item label="任务名称"><el-input v-model="form.name" :disabled="readonly"/></el-form-item>
      <template v-if="escortMode">
        <el-form-item label="护航目标"><el-input v-model="form.escortTargetName" :disabled="readonly"/></el-form-item>
        <el-form-item label="预设航线"><el-select v-model="form.routePreset" :disabled="readonly"><el-option label="灯塔海域安全航线" value="LIGHTHOUSE_SAFE_ROUTE"/><el-option label="近岸巡航航线" value="COASTAL_PATROL_ROUTE"/></el-select></el-form-item>
        <el-form-item label="航行速度"><el-select v-model="form.escortSpeed" :disabled="readonly"><el-option label="低速" value="LOW"/><el-option label="中速" value="MEDIUM"/></el-select></el-form-item>
        <el-form-item label="威胁初始方向"><el-select v-model="form.threatDirection" :disabled="readonly"><el-option label="右前方" value="front_right"/><el-option label="正前方" value="front"/><el-option label="左前方" value="front_left"/><el-option label="正右方" value="right"/><el-option label="正左方" value="left"/></el-select></el-form-item>
        <el-form-item label="威胁出现方式"><el-select v-model="form.threatMode" :disabled="readonly"><el-option label="自动出现" value="AUTO"/><el-option label="2D 地图点击放置" value="MAP_CLICK"/></el-select></el-form-item>
      </template>
      <template v-else>
        <el-form-item label="围捕目标"><el-input v-model="form.targetName" :disabled="readonly"/></el-form-item>
        <el-form-item label="目标运动方式"><el-select v-model="form.targetBehavior" :disabled="readonly"><el-option label="低速机动" value="MOVING"/><el-option label="静止目标" value="STATIC"/></el-select></el-form-item>
      </template>
      <el-form-item label="任务区域"><el-input v-model="form.missionArea" :disabled="readonly"/></el-form-item>
      <el-form-item label="任务说明" class="wide"><el-input v-model="form.description" type="textarea" :rows="3" :disabled="readonly"/></el-form-item>
    </el-form>
    <section class="algorithm-card"><div class="mark"><component :is="escortMode ? Shield : Target" :size="24"/></div><div><span>当前执行算法</span><h4>{{ selectedAlgorithm?.name }}</h4><p>{{ selectedAlgorithm?.description }}</p></div><b><CheckCircle2 :size="15"/>可执行</b></section>
    <section class="fleet-card" :class="{warning:!fleetReady}"><header><div><span>固定设备映射</span><h4>3 UAV + 3 USV</h4></div><b>{{ fleetReady ? '编组完整' : '设备数量不足' }}</b></header><div class="fleet-summary"><article><Plane :size="20"/><div><strong>无人机</strong><span>UAV-01 / UAV-02 / UAV-03</span></div><em>{{ uavCount }}/3</em></article><article><Ship :size="20"/><div><strong>无人艇</strong><span>USV-01 / USV-02 / USV-03</span></div><em>{{ usvCount }}/3</em></article></div><p v-if="escortMode"><Route :size="14"/>护航目标沿安全航线移动，威胁出现后动态重编队。</p></section>
    <template #footer><el-button @click="emit('update:modelValue',false)">关闭</el-button><template v-if="!readonly"><el-button :loading="saving" @click="emit('save',buildPayload('DRAFT'))">保存草稿</el-button><el-button type="primary" :disabled="!fleetReady||!selectedAlgorithm" :loading="saving" @click="emit('save',buildPayload('READY'))">保存为待执行</el-button></template></template>
  </el-dialog>
</template>

<style scoped>
.config-intro{padding:2px 0 14px;border-bottom:1px solid rgba(108,228,213,.16)}.config-intro>span{display:flex;align-items:center;gap:6px;color:#55d9e9;font-size:10px;font-weight:900;letter-spacing:.12em}.config-intro h3{margin:6px 0 4px;color:#efffff;font-size:19px}.config-intro p{margin:0;color:#7f9fa3;font-size:12px}.config-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px;margin-top:14px}.config-form .wide{grid-column:1/-1}.config-form :deep(.el-select){width:100%}.config-form :deep(.el-select-dropdown__item small){float:right;color:#718f94}.algorithm-card{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:12px;align-items:center;padding:13px;background:#071d26;border:1px solid rgba(85,231,167,.32);border-radius:7px}.mark{display:grid;width:48px;height:48px;place-items:center;color:#58dceb;background:rgba(75,197,219,.08);border:1px solid rgba(75,197,219,.2);border-radius:7px}.algorithm-card span,.algorithm-card h4,.algorithm-card p{display:block;margin:0}.algorithm-card span{color:#668b90;font-size:9px}.algorithm-card h4{margin-top:3px;color:#eafffb;font-size:14px}.algorithm-card p{margin-top:4px;color:#76989c;font-size:10px}.algorithm-card>b{display:flex;align-items:center;gap:5px;color:#55e7a7;font-size:10px}.fleet-card{margin-top:10px;padding:13px;background:#061a23;border:1px solid rgba(82,177,198,.2);border-radius:7px}.fleet-card.warning{border-color:rgba(255,116,116,.45)}.fleet-card header{display:flex;justify-content:space-between;align-items:center}.fleet-card header span{color:#51d6e8;font-size:9px;font-weight:900;letter-spacing:.1em}.fleet-card h4{margin:3px 0;color:#efffff}.fleet-card header>b{color:#55e7a7;font-size:10px}.fleet-card.warning header>b{color:#ff7474}.fleet-summary{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.fleet-summary article{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px;color:#57d9e9;background:rgba(74,151,164,.05);border:1px solid rgba(79,158,172,.12);border-radius:5px}.fleet-summary strong,.fleet-summary span{display:block}.fleet-summary strong{color:#dff5f3;font-size:11px}.fleet-summary span{margin-top:2px;color:#708f93;font-size:9px}.fleet-summary em{color:#55e7a7;font-size:11px;font-style:normal}.fleet-card>p{display:flex;align-items:center;gap:6px;margin:10px 0 0;color:#7fa2a5;font-size:10px}@media(max-width:700px){.config-form,.fleet-summary{grid-template-columns:1fr}}
</style>
