<script setup lang="ts">
import { Activity, Beaker, CalendarClock, Copy, FilePenLine, Play, ScrollText, Trash2 } from '@lucide/vue'
import type { Mission, MissionStatus } from '@/types/mission'

defineProps<{ missions: Mission[]; loading?: boolean }>()
const emit = defineEmits<{
  action: [action: 'configure' | 'view' | 'start' | 'execute' | 'events' | 'copy' | 'delete' | 'retry' | 'result', mission: Mission]
}>()

function actions(mission: Mission) {
  if (mission.status === 'DRAFT') return [['configure', '继续配置'], ['copy', '复制'], ['delete', '删除']] as const
  if (mission.status === 'READY') return [['view', '查看配置'], ['configure', '编辑配置'], ['start', '执行任务']] as const
  if (mission.status === 'RUNNING' || mission.status === 'PAUSED') return [['execute', '查看执行'], ['events', '运行事件']] as const
  if (mission.status === 'FAILED') return [['events', '异常记录'], ['retry', '再次执行']] as const
  return [['events', '执行记录'], ['retry', '再次执行']] as const
}

const statusLabels: Record<MissionStatus, string> = {
  DRAFT: '配置中',
  READY: '待执行',
  RUNNING: '运行中',
  PAUSED: '已暂停',
  COMPLETED: '已完成',
  FAILED: '异常',
  CANCELLED: '已终止',
}

const typeLabels = {
  COOPERATIVE_ENCIRCLEMENT: '协同围捕',
  TARGET_INSPECTION: '目标巡检',
  PATH_TRACKING: '路径跟踪',
  COMMUNICATION_RELAY: '通信中继',
  CUSTOM: '自定义实验',
}

const modeLabels = {
  UNITY_STANDALONE: '任务中心独立 Unity',
  ROS_GAZEBO: 'ROS / Gazebo',
  HYBRID_MIRROR: '混合镜像',
}

function actionIcon(action: string) {
  return {
    configure: FilePenLine,
    view: ScrollText,
    start: Play,
    execute: Activity,
    events: ScrollText,
    copy: Copy,
    delete: Trash2,
    retry: Beaker,
    result: Beaker,
  }[action]
}
</script>

<template>
  <div v-loading="loading" class="mission-list-panel">
    <article v-for="mission in missions" :key="mission.id" class="mission-list-card" :class="mission.status.toLowerCase()">
      <header>
        <div class="mission-list-title">
          <span class="mission-list-symbol"><Beaker :size="19" /></span>
          <div><small>{{ mission.code }}</small><h3>{{ mission.name }}</h3></div>
        </div>
        <b>{{ statusLabels[mission.status] }}</b>
      </header>
      <div class="mission-list-meta">
        <div><span>算法版本</span><strong>Unity 默认简单围捕 v1.0</strong></div>
        <div><span>运行环境</span><strong>{{ modeLabels[mission.executionMode] }}</strong></div>
        <div><span>设备编组</span><strong>{{ mission.deviceCount || 0 }} 台载具</strong></div>
        <div><span>任务类型</span><strong>{{ typeLabels[mission.type] }}</strong></div>
      </div>
      <p>{{ mission.description || `${typeLabels[mission.type]}实验，目标区域：${mission.missionArea || '待配置'}` }}</p>
      <footer>
        <span><CalendarClock :size="13" /> 更新于 {{ new Date(mission.updatedAt).toLocaleString() }}</span>
        <div>
          <button
            v-for="[action, label] in actions(mission)"
            :key="action"
            type="button"
            :class="{ primary: ['start', 'execute', 'retry'].includes(action), danger: action === 'delete' }"
            @click="emit('action', action, mission)"
          >
            <component :is="actionIcon(action)" :size="14" />{{ label }}
          </button>
        </div>
      </footer>
    </article>
    <el-empty v-if="!loading && !missions.length" description="暂无符合条件的任务" />
  </div>
</template>

<style scoped>
.mission-list-panel{display:grid;gap:10px}.mission-list-card{position:relative;padding:16px 18px;border:1px solid rgba(108,228,213,.2);border-radius:9px;background:linear-gradient(135deg,rgba(5,28,38,.98),rgba(3,18,26,.94));box-shadow:0 16px 36px rgba(0,0,0,.16);overflow:hidden}.mission-list-card::before{position:absolute;left:0;top:0;width:3px;height:100%;content:"";background:#43cfe2}.mission-list-card.ready::before{background:#ffc93e}.mission-list-card.running::before,.mission-list-card.paused::before{background:#55e7a7}.mission-list-card.failed::before,.mission-list-card.cancelled::before{background:#ff6969}.mission-list-card header,.mission-list-card footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.mission-list-title{display:flex;align-items:center;gap:11px}.mission-list-symbol{display:grid;width:38px;height:38px;place-items:center;color:#65ddeb;background:rgba(70,205,228,.08);border:1px solid rgba(70,205,228,.24);border-radius:7px}.mission-list-card h3{margin:4px 0;font-size:17px}.mission-list-card small{color:#54d7e5}.mission-list-card header>b{font-size:11px;color:#6ce4d5;border:1px solid currentColor;padding:5px 9px;border-radius:4px}.mission-list-card.running header>b,.mission-list-card.paused header>b{color:#55e7a7}.mission-list-card.ready header>b{color:#ffc93e}.mission-list-card.failed header>b,.mission-list-card.cancelled header>b{color:#ff6969}.mission-list-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:13px 0}.mission-list-meta div{padding:9px 10px;background:rgba(87,166,179,.045);border:1px solid rgba(95,172,183,.12);border-radius:5px}.mission-list-meta span,.mission-list-meta strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mission-list-meta span{color:#6f9093;font-size:10px}.mission-list-meta strong{margin-top:4px;color:#d9f6f4;font-size:11px}.mission-list-card p{color:#8faeb1;font-size:12px;margin:8px 0 14px}.mission-list-card footer>span{display:flex;align-items:center;gap:5px;color:#678a90;font-size:11px}.mission-list-card footer>div{display:flex;gap:7px}.mission-list-card button{display:inline-flex;align-items:center;gap:5px;height:32px;padding:0 11px;border:1px solid #2c5660;border-radius:5px;background:#08222c;color:#cfe7e7;cursor:pointer}.mission-list-card button:hover{border-color:#6ce4d5;color:#6ce4d5}.mission-list-card button.primary{border-color:rgba(82,210,229,.52);background:#145b69;color:#efffff}.mission-list-card button.danger{border-color:rgba(255,105,105,.35);color:#ff8b8b}@media(max-width:1050px){.mission-list-meta{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:720px){.mission-list-card footer{align-items:flex-start;flex-direction:column}.mission-list-meta{grid-template-columns:1fr}}
</style>
