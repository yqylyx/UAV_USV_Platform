<script setup lang="ts">
import { computed } from 'vue'
import type { MissionPreflight } from '@/types/mission'

const props = defineProps<{ modelValue: boolean; check: MissionPreflight | null; trajectoryLive: boolean; loading?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; confirm: [] }>()
const canConfirm = computed(() => !!props.check?.canStart)
</script>

<template>
  <el-dialog :model-value="modelValue" title="实验任务启动检查" width="660px" class="mission-preflight-dialog" @update:model-value="emit('update:modelValue', $event)">
    <div class="preflight-hero">
      <div><span>MISSION PREFLIGHT</span><h3>创建独立 RUN 前检查任务配置与运行环境</h3></div>
      <b :class="{ ready: canConfirm }">{{ canConfirm ? '可以启动' : '存在阻断项' }}</b>
    </div>
    <div v-loading="loading" class="preflight-list">
      <div :class="{ ok: check?.configurationComplete }"><span>任务配置完整</span><b>{{ check?.configurationComplete ? '通过' : '失败' }}</b></div>
      <div :class="{ ok: !!check?.executionMode }"><span>运行模式</span><b>{{ check?.executionMode || '--' }}</b></div>
      <div :class="{ ok: check && check.requiredDeviceCount === check.onlineRequiredDeviceCount }"><span>Unity 载具识别</span><b>{{ check ? `${check.onlineRequiredDeviceCount}/${check.requiredDeviceCount}` : '--' }}</b></div>
      <div :class="{ ok: check?.unityOnline }"><span>任务中心 Unity</span><b>{{ check?.unityOnline ? '在线' : '离线' }}</b></div>
      <div :class="{ ok: check?.unityControlsReady }"><span>Unity 指令桥</span><b>{{ check?.unityControlsReady ? '就绪' : '未就绪' }}</b></div>
      <div :class="{ ok: !!check?.unityTrajectorySequence }"><span>真实轨迹帧</span><b>{{ check?.unityTrajectorySequence ? `#${check.unityTrajectorySequence}` : '等待中' }}</b></div>
      <div :class="{ ok: check && !check.hasOpenRun }"><span>开放执行批次</span><b>{{ check?.hasOpenRun ? '已存在' : '无' }}</b></div>
      <div :class="{ ok: trajectoryLive }"><span>Unity 实时轨迹</span><b>{{ trajectoryLive ? '可用' : '等待首帧，不阻断启动' }}</b></div>
      <p v-for="issue in check?.issues || []" :key="issue.code" :class="issue.level.toLowerCase()">{{ issue.message }}</p>
    </div>
    <div class="preflight-note">确认后将创建任务中心独立运行批次，并只向 MISSION_CENTER Unity 实例下发开始指令，不影响系统总览。</div>
    <template #footer><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :disabled="!canConfirm" @click="emit('confirm')">确认并开始任务</el-button></template>
  </el-dialog>
</template>

<style scoped>
.preflight-hero{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px;padding:13px;background:linear-gradient(135deg,#071f2a,#05151d);border:1px solid rgba(76,184,211,.24);border-radius:7px}.preflight-hero span{color:#53d8eb;font-size:9px;font-weight:900;letter-spacing:.13em}.preflight-hero h3{margin:4px 0 0;color:#efffff;font-size:15px}.preflight-hero>b{color:#ff7676;font-size:11px}.preflight-hero>b.ready{color:#55e7a7}.preflight-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.preflight-list>div{display:flex;justify-content:space-between;gap:10px;padding:11px;border:1px solid rgba(255,105,105,.34);background:rgba(255,80,80,.05);border-radius:5px}.preflight-list>div.ok{border-color:rgba(85,231,167,.3)}.preflight-list b{color:#ff7474;font-size:11px;text-align:right}.preflight-list .ok b{color:#55e7a7}.preflight-list p{grid-column:1/-1;margin:0;padding:8px;color:#ffcc66;background:rgba(255,190,60,.07)}.preflight-list p.error{color:#ff7474}.preflight-note{margin-top:12px;padding:10px;color:#7e9fa3;font-size:10px;line-height:1.7;background:rgba(74,154,168,.06);border-left:3px solid #4ccde2}@media(max-width:650px){.preflight-list{grid-template-columns:1fr}}
</style>
