<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { CheckCircle2, Cpu, Plane, Ship, Sparkles } from '@lucide/vue'
import type { Device } from '@/types/device'
import type { MissionDetail, MissionDeviceRole, MissionSavePayload, MissionStatus, MissionType } from '@/types/mission'

const props = defineProps<{ modelValue: boolean; detail: MissionDetail | null; devices: Device[]; readonly?: boolean; saving?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; save: [payload: MissionSavePayload] }>()

const form = reactive({
  code: '',
  name: '',
  type: 'COOPERATIVE_ENCIRCLEMENT' as MissionType,
  targetName: 'TARGET',
  missionArea: '灯塔海域',
  description: '三机三艇协同围捕实验',
})

watch(() => [props.modelValue, props.detail] as const, () => {
  if (!props.modelValue) return
  const mission = props.detail?.mission
  Object.assign(form, {
    code: mission?.code || `EXP-${Date.now()}`,
    name: mission?.name || '三机三艇协同围捕实验',
    type: mission?.type || 'COOPERATIVE_ENCIRCLEMENT',
    targetName: mission?.targetName || 'TARGET',
    missionArea: mission?.missionArea || '灯塔海域',
    description: mission?.description || '使用任务中心独立 Unity 执行三机三艇简单围捕。',
  })
}, { immediate: true })

const fleet = computed(() => props.devices
  .filter(device => device.type === 'UAV' || device.type === 'USV')
  .sort((left, right) => left.code.localeCompare(right.code)))
const uavCount = computed(() => fleet.value.filter(device => device.type === 'UAV').length)
const usvCount = computed(() => fleet.value.filter(device => device.type === 'USV').length)
const fleetReady = computed(() => uavCount.value >= 3 && usvCount.value >= 3)

function roleFor(device: Device, typeIndex: number): MissionDeviceRole {
  if (device.type === 'UAV') return typeIndex === 0 ? 'UAV_RECON' : 'UAV_TRACK'
  return typeIndex === 0 ? 'USV_INTERCEPT' : 'USV_BLOCKADE'
}

function buildPayload(status: MissionStatus): MissionSavePayload {
  const selected = [
    ...fleet.value.filter(device => device.type === 'UAV').slice(0, 3),
    ...fleet.value.filter(device => device.type === 'USV').slice(0, 3),
  ]
  return {
    code: form.code,
    name: form.name,
    type: 'COOPERATIVE_ENCIRCLEMENT',
    executionMode: 'UNITY_STANDALONE',
    status,
    stage: 'PREPARE',
    priority: 1,
    targetName: form.targetName,
    targetBehavior: '移动目标',
    missionArea: form.missionArea,
    plannedStartAt: null,
    plannedEndAt: null,
    description: form.description,
    devices: selected.map(device => {
      const sameType = selected.filter(item => item.type === device.type)
      return {
        deviceId: device.id,
        role: roleFor(device, sameType.findIndex(item => item.id === device.id)),
        callSign: device.code,
        required: true,
        notes: '任务中心简单围捕自动编组',
      }
    }),
    parameters: [],
  }
}
</script>

<template>
  <el-dialog :model-value="modelValue" title="简单围捕任务" width="820px" top="6vh" class="mission-config-dialog" @update:model-value="emit('update:modelValue', $event)">
    <div class="simple-config-intro">
      <span><Sparkles :size="16" /> UNITY SIMPLE ENCIRCLEMENT</span>
      <h3>创建三机三艇简单围捕任务</h3>
      <p>不需要手动配置角色、呼号和运行参数。系统会自动使用 UAV-01~03 与 USV-01~03。</p>
    </div>

    <el-form label-position="top" class="simple-config-form">
      <el-form-item label="任务编号"><el-input v-model="form.code" :disabled="readonly" /></el-form-item>
      <el-form-item label="任务名称"><el-input v-model="form.name" :disabled="readonly" /></el-form-item>
      <el-form-item label="围捕目标"><el-input v-model="form.targetName" :disabled="readonly" /></el-form-item>
      <el-form-item label="任务区域"><el-input v-model="form.missionArea" :disabled="readonly" /></el-form-item>
      <el-form-item label="任务说明" class="wide"><el-input v-model="form.description" type="textarea" :rows="3" :disabled="readonly" /></el-form-item>
    </el-form>

    <section class="simple-algorithm-card">
      <div class="algorithm-mark"><Cpu :size="24" /></div>
      <div><span>当前执行算法</span><h4>Unity 默认简单围捕</h4><p>UnityNativeAdapter · missionStart / missionPause / missionResume / missionCancel</p></div>
      <b><CheckCircle2 :size="15" />可执行</b>
    </section>

    <section class="simple-fleet-card" :class="{ warning: !fleetReady }">
      <header><div><span>自动编组</span><h4>固定使用 3 UAV + 3 USV</h4></div><b>{{ fleetReady ? '编组完整' : '设备数量不足' }}</b></header>
      <div class="fleet-summary">
        <article><Plane :size="20" /><div><strong>无人机</strong><span>UAV-01 / UAV-02 / UAV-03</span></div><em>{{ Math.min(uavCount, 3) }}/3</em></article>
        <article><Ship :size="20" /><div><strong>无人艇</strong><span>USV-01 / USV-02 / USV-03</span></div><em>{{ Math.min(usvCount, 3) }}/3</em></article>
      </div>
    </section>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <template v-if="!readonly">
        <el-button :loading="saving" @click="emit('save', buildPayload('DRAFT'))">保存草稿</el-button>
        <el-button type="primary" :disabled="!fleetReady" :loading="saving" @click="emit('save', buildPayload('READY'))">保存为待执行</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.simple-config-intro{padding:2px 0 15px;border-bottom:1px solid rgba(108,228,213,.16)}.simple-config-intro>span{display:flex;align-items:center;gap:6px;color:#55d9e9;font-size:10px;font-weight:900;letter-spacing:.12em}.simple-config-intro h3{margin:6px 0 4px;color:#efffff;font-size:19px}.simple-config-intro p{color:#7f9fa3;font-size:12px}.simple-config-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px;margin-top:15px}.simple-config-form .wide{grid-column:1/-1}.simple-algorithm-card{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:12px;align-items:center;padding:13px;background:#071d26;border:1px solid rgba(85,231,167,.32);border-radius:7px}.algorithm-mark{display:grid;width:48px;height:48px;place-items:center;color:#58dceb;background:rgba(75,197,219,.08);border:1px solid rgba(75,197,219,.2);border-radius:7px}.simple-algorithm-card span,.simple-algorithm-card h4,.simple-algorithm-card p{display:block;margin:0}.simple-algorithm-card span{color:#668b90;font-size:9px}.simple-algorithm-card h4{margin-top:3px;color:#eafffb;font-size:14px}.simple-algorithm-card p{margin-top:4px;color:#76989c;font-size:10px}.simple-algorithm-card>b{display:flex;align-items:center;gap:5px;color:#55e7a7;font-size:10px}.simple-fleet-card{margin-top:10px;padding:13px;background:#061a23;border:1px solid rgba(82,177,198,.2);border-radius:7px}.simple-fleet-card.warning{border-color:rgba(255,116,116,.45)}.simple-fleet-card header{display:flex;justify-content:space-between;align-items:center}.simple-fleet-card header span{color:#51d6e8;font-size:9px;font-weight:900;letter-spacing:.1em}.simple-fleet-card h4{margin:3px 0;color:#efffff}.simple-fleet-card header>b{color:#55e7a7;font-size:10px}.simple-fleet-card.warning header>b{color:#ff7474}.fleet-summary{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.fleet-summary article{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px;color:#57d9e9;background:rgba(74,151,164,.05);border:1px solid rgba(79,158,172,.12);border-radius:5px}.fleet-summary strong,.fleet-summary span{display:block}.fleet-summary strong{color:#dff5f3;font-size:11px}.fleet-summary span{margin-top:2px;color:#708f93;font-size:9px}.fleet-summary em{color:#55e7a7;font-size:11px;font-style:normal}@media(max-width:700px){.simple-config-form,.fleet-summary{grid-template-columns:1fr}}
</style>
