<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchMissionEvents } from '@/api/mission'
import type { MissionEvent, MissionEventLevel } from '@/types/mission'

const props = defineProps<{ modelValue: boolean; missionId: number | null; runId?: number | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const events = ref<MissionEvent[]>([])
const level = ref<MissionEventLevel | undefined>()
const loading = ref(false)
async function refresh(){if(!props.missionId)return;loading.value=true;try{events.value=await fetchMissionEvents(props.missionId,{runId:props.runId??undefined,level:level.value,limit:100})}finally{loading.value=false}}
watch(() => props.modelValue, value => { if(value) void refresh() })
</script>
<template>
  <el-drawer :model-value="modelValue" title="任务事件" size="480px" @update:model-value="emit('update:modelValue',$event)">
    <div class="event-tools"><el-select v-model="level" clearable placeholder="全部级别" @change="refresh"><el-option label="信息" value="INFO"/><el-option label="警告" value="WARNING"/><el-option label="错误" value="ERROR"/></el-select><el-button @click="refresh">刷新</el-button></div>
    <div v-loading="loading" class="event-list"><article v-for="event in events" :key="event.id" :class="event.level.toLowerCase()"><header><b>{{ event.title }}</b><time>{{ new Date(event.occurredAt).toLocaleString() }}</time></header><p>{{ event.message || '--' }}</p><footer>{{ event.eventType }} · {{ event.source || '--' }} · {{ event.stage || '--' }}</footer></article></div>
  </el-drawer>
</template>
<style scoped>.event-tools{display:flex;gap:8px;margin-bottom:12px}.event-list{display:grid;gap:9px}.event-list article{padding:12px;border-left:3px solid #54d7e5;background:#071d26}.event-list article.warning{border-color:#ffc84d}.event-list article.error{border-color:#ff6969}.event-list header{display:flex;justify-content:space-between;gap:10px}.event-list time,.event-list footer{color:#6f9297;font-size:11px}.event-list p{color:#b8cecf}</style>
