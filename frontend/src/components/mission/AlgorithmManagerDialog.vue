<script setup lang="ts">
import { computed, ref } from 'vue'
import { Cpu, Crown, Power, Shield, Target } from '@lucide/vue'
import type { AlgorithmDefinition } from '@/types/mission'

const props = defineProps<{ modelValue: boolean; algorithms: AlgorithmDefinition[]; loading?: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  toggle: [algorithm: AlgorithmDefinition, enabled: boolean]
  setDefault: [algorithm: AlgorithmDefinition]
}>()
const selectedCode = ref('')
const selected = computed(() => props.algorithms.find(item => item.code === selectedCode.value) ?? props.algorithms[0])
const typeLabel = (value: string) => value === 'COOPERATIVE_ESCORT' ? '协同护航' : '协同围捕'
</script>

<template>
  <el-dialog :model-value="modelValue" title="算法管理" width="920px" top="7vh" @update:model-value="emit('update:modelValue',$event)">
    <div class="manager-layout" v-loading="loading">
      <section class="algorithm-list">
        <header><span>ALGORITHM CATALOG</span><h3>任务中心算法目录</h3><p>任务配置只显示已启用算法；默认算法用于新建对应类型任务。</p></header>
        <button v-for="algorithm in algorithms" :key="algorithm.code" :class="{active:selected?.code===algorithm.code,disabled:!algorithm.enabled}" @click="selectedCode=algorithm.code">
          <span class="algorithm-icon"><component :is="algorithm.missionType==='COOPERATIVE_ESCORT'?Shield:Target" :size="20"/></span>
          <span><b>{{ algorithm.name }}</b><small>{{ algorithm.code }} · v{{ algorithm.version }}</small></span>
          <em>{{ algorithm.enabled ? '已启用' : '已停用' }}</em>
        </button>
      </section>
      <section v-if="selected" class="algorithm-detail">
        <div class="detail-mark"><Cpu :size="29"/></div><span>ALGORITHM PROFILE</span><h2>{{ selected.name }}</h2><p>{{ selected.description }}</p>
        <dl><div><dt>算法编码</dt><dd>{{ selected.code }}</dd></div><div><dt>版本</dt><dd>v{{ selected.version }}</dd></div><div><dt>任务类型</dt><dd>{{ typeLabel(selected.missionType) }}</dd></div><div><dt>执行适配器</dt><dd>{{ selected.adapterType }}</dd></div><div><dt>设备规模</dt><dd>{{ selected.deviceScale }}</dd></div><div><dt>默认算法</dt><dd>{{ selected.defaultForType?'是':'否' }}</dd></div></dl>
        <div class="manager-actions"><button :class="{danger:selected.enabled}" :disabled="selected.defaultForType&&selected.enabled" @click="emit('toggle',selected,!selected.enabled)"><Power :size="16"/>{{ selected.enabled?'停用算法':'启用算法' }}</button><button :disabled="!selected.enabled||selected.defaultForType" @click="emit('setDefault',selected)"><Crown :size="16"/>设为该任务类型默认</button></div>
        <small v-if="selected.defaultForType&&selected.enabled">默认算法不能直接停用，请先将同类型其他算法设为默认。</small>
      </section>
    </div>
    <template #footer><el-button @click="emit('update:modelValue',false)">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.manager-layout{display:grid;grid-template-columns:1.05fr .95fr;gap:12px;min-height:440px}.algorithm-list,.algorithm-detail{padding:15px;background:#061a23;border:1px solid rgba(76,173,195,.22);border-radius:8px}.algorithm-list header{padding-bottom:12px;border-bottom:1px solid rgba(77,172,190,.17)}.algorithm-list header span,.algorithm-detail>span{color:#50d5e7;font-size:9px;font-weight:900;letter-spacing:.13em}.algorithm-list h3{margin:5px 0 3px;color:#eafffb}.algorithm-list p,.algorithm-detail p{margin:0;color:#78999d;font-size:11px}.algorithm-list>button{display:grid;width:100%;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:9px;margin-top:9px;padding:10px;text-align:left;color:#dff3f2;background:#071f29;border:1px solid rgba(73,157,173,.18);border-radius:6px;cursor:pointer}.algorithm-list>button.active{border-color:#58dce9;background:#092833}.algorithm-list>button.disabled{opacity:.55}.algorithm-icon{display:grid;width:40px;height:40px;place-items:center;color:#5eddea;border:1px solid rgba(87,218,234,.22);border-radius:6px}.algorithm-list b,.algorithm-list small{display:block}.algorithm-list small{margin-top:4px;color:#6d8f94;font-size:9px}.algorithm-list em{color:#55e7a7;font-size:9px;font-style:normal}.algorithm-list .disabled em{color:#ff8b8b}.algorithm-detail{position:relative}.detail-mark{display:grid;width:58px;height:58px;margin-bottom:14px;place-items:center;color:#58dce9;background:rgba(71,195,217,.08);border:1px solid rgba(71,195,217,.24);border-radius:8px}.algorithm-detail h2{margin:6px 0;color:#efffff;font-size:20px}.algorithm-detail>p{min-height:38px}.algorithm-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:18px 0}.algorithm-detail dl div{padding:9px;background:rgba(67,148,162,.05);border:1px solid rgba(67,148,162,.13);border-radius:5px}.algorithm-detail dt{color:#6e9297;font-size:9px}.algorithm-detail dd{margin:4px 0 0;color:#dcefee;font-size:11px}.manager-actions{display:grid;gap:8px}.manager-actions button{display:flex;align-items:center;justify-content:center;gap:7px;height:36px;color:#dff5f3;background:#0a2a35;border:1px solid #315e68;border-radius:5px;cursor:pointer}.manager-actions button.danger{color:#ff8d8d;border-color:#773c43}.manager-actions button:disabled{cursor:not-allowed;opacity:.4}.algorithm-detail>small{display:block;margin-top:10px;color:#7d9ca0;font-size:9px}@media(max-width:760px){.manager-layout{grid-template-columns:1fr}.algorithm-detail dl{grid-template-columns:1fr}}
</style>
