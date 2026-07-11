<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    missionName?: string
    status?: string
    busy?: boolean
    progress?: number
  }>(),
  {
    missionName: '三机三艇协同围捕',
    status: 'READY',
    busy: false,
    progress: 0,
  },
)

const emit = defineEmits<{
  action: [action: 'deploy' | 'start' | 'pause' | 'resume' | 'return' | 'abort']
}>()

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    DRAFT: '草稿',
    READY: '待部署',
    RUNNING: '运行中',
    PAUSED: '已暂停',
    COMPLETED: '已完成',
    FAILED: '异常',
    CANCELLED: '已取消',
  }
  return labels[status] ?? status
}
</script>

<template>
  <article class="mission-group-control">
    <header>
      <div>
        <span>MISSION GROUP</span>
        <strong>任务编组控制</strong>
      </div>
      <b>{{ statusLabel(status) }}</b>
    </header>
    <p>{{ missionName }}</p>
    <div class="progress-track"><i :style="{ width: `${Math.max(0, Math.min(100, progress))}%` }"></i></div>
    <div class="mission-actions">
      <button type="button" :disabled="busy" @click="emit('action', 'deploy')">编组部署</button>
      <button v-if="status === 'DRAFT' || status === 'READY'" type="button" class="primary" :disabled="busy" @click="emit('action', 'start')">开始任务</button>
      <button v-if="status === 'RUNNING'" type="button" :disabled="busy" @click="emit('action', 'pause')">暂停任务</button>
      <button v-if="status === 'PAUSED'" type="button" class="primary" :disabled="busy" @click="emit('action', 'resume')">继续任务</button>
      <button type="button" :disabled="busy" @click="emit('action', 'return')">全体返航</button>
    </div>
    <button type="button" class="abort" :disabled="busy" @click="emit('action', 'abort')">终止任务</button>
  </article>
</template>

<style scoped>
.mission-group-control {
  padding: 14px;
  background: linear-gradient(145deg, rgba(6, 29, 38, 0.98), rgba(7, 18, 27, 0.96));
  border: 1px solid rgba(65, 202, 239, 0.48);
  border-radius: 10px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

header span,
header strong {
  display: block;
}

header span {
  color: #4bd5ef;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.16em;
}

header strong {
  margin-top: 2px;
  color: #efffff;
  font-size: 15px;
}

header b {
  color: #69e6a1;
  font-size: 11px;
}

p {
  margin: 10px 0 8px;
  color: #8fb1b0;
  font-size: 11px;
}

.progress-track {
  height: 4px;
  overflow: hidden;
  background: rgba(110, 169, 174, 0.16);
  border-radius: 999px;
}

.progress-track i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #2ec7e6, #77ead8);
}

.mission-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  margin-top: 11px;
}

button {
  min-height: 36px;
  color: #dff8f4;
  font: inherit;
  font-size: 11px;
  font-weight: 900;
  cursor: pointer;
  background: rgba(60, 184, 215, 0.08);
  border: 1px solid rgba(75, 213, 239, 0.3);
  border-radius: 5px;
}

button.primary,
button:hover:not(:disabled) {
  color: #061216;
  background: #4bd5ef;
}

button.abort {
  width: 100%;
  min-height: 32px;
  margin-top: 7px;
  color: #ff817b;
  background: rgba(255, 75, 69, 0.06);
  border-color: rgba(255, 91, 84, 0.55);
}

button.abort:hover:not(:disabled) {
  color: #fff;
  background: #d83d3a;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
</style>
