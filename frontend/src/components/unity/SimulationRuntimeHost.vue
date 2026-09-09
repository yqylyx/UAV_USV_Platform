<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, watch } from 'vue'
import SimulationUnityWebglPanel from './SimulationUnityWebglPanel.vue'
import { simulationRuntime, setTacticalNoticesVisible } from '@/composables/simulationRuntime'

const props = defineProps<{ active: boolean }>()
const panel = simulationRuntime.panel
const frameStyle = reactive({ left: '-10000px', top: '0px', width: '1280px', height: '720px', zIndex: '20' })
let viewport: HTMLElement | null = null
let observer: ResizeObserver | null = null
let animationFrame = 0
let settleTimer = 0
let trackUntil = 0

function align() {
  const target = props.active
    ? document.querySelector<HTMLElement>('[data-simulation-viewport]') : null
  if (target !== viewport) {
    observer?.disconnect()
    viewport = target
    if (viewport) observer?.observe(viewport)
  }
  const rect = viewport?.getBoundingClientRect()
  if (!rect || rect.width < 1 || rect.height < 1) {
    // Never detach or reduce the render target to zero while parked.
    if (frameStyle.left !== '-10000px') frameStyle.left = '-10000px'
    return
  }
  const nextFrame = {
    left: `${rect.left}px`, top: `${rect.top}px`,
    width: `${Math.round(rect.width)}px`, height: `${Math.round(rect.height)}px`,
    zIndex: viewport?.closest('.expanded') ? '2101' : '20',
  }
  // Resize tracking runs once per animation frame during drawer/fullscreen
  // transitions. Avoid reactive writes and Unity viewport syncs when the
  // measured rectangle did not actually change; this keeps the WebGL main
  // thread free for rendering instead of doing redundant layout work.
  if (Object.entries(nextFrame).every(
    ([key, value]) => frameStyle[key as keyof typeof frameStyle] === value,
  )) return
  Object.assign(frameStyle, nextFrame)
  window.clearTimeout(settleTimer)
  settleTimer = window.setTimeout(() => panel.value?.syncViewport(), 140)
}

function track() {
  trackUntil = performance.now() + 600
  window.cancelAnimationFrame(animationFrame)
  void nextTick(() => {
    const tick = () => {
      align()
      if (performance.now() < trackUntil) animationFrame = requestAnimationFrame(tick)
    }
    animationFrame = requestAnimationFrame(tick)
  })
}

function finishLayoutTransition(event: Event) {
  // ResizeObserver sees size, not a position-only change of an ancestor.
  if (viewport && event.target instanceof Element && event.target.contains(viewport)) track()
}

watch(() => props.active, track)
watch(() => props.active && !simulationRuntime.recovering.value,
  setTacticalNoticesVisible, { immediate: true })
onMounted(() => {
  observer = new ResizeObserver(align)
  window.addEventListener('resize', track)
  window.addEventListener('scroll', align, true)
  window.addEventListener('unity-runtime-track', track)
  document.addEventListener('transitionend', finishLayoutTransition, true)
  document.addEventListener('transitioncancel', finishLayoutTransition, true)
  track()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  cancelAnimationFrame(animationFrame)
  clearTimeout(settleTimer)
  window.removeEventListener('resize', track)
  window.removeEventListener('scroll', align, true)
  window.removeEventListener('unity-runtime-track', track)
  document.removeEventListener('transitionend', finishLayoutTransition, true)
  document.removeEventListener('transitioncancel', finishLayoutTransition, true)
  panel.value = null
})
</script>

<template>
  <div class="simulation-runtime-host" :class="{ active }" :style="frameStyle" :inert="!active">
    <SimulationUnityWebglPanel ref="panel"
      @unity-ready="simulationRuntime.events?.ready()"
      @unity-loading="simulationRuntime.events?.loading()"
      @unity-message="simulationRuntime.events?.message($event)"
      @unity-error="simulationRuntime.events?.error($event)" />
    <div class="tactical-notice-stack" role="status" aria-live="polite" aria-atomic="true">
      <Transition name="tactical-strip" mode="out-in">
      <article
        v-if="simulationRuntime.tacticalNotices.value[0]"
        :key="simulationRuntime.tacticalNotices.value[0].eventId"
        :class="`event-${simulationRuntime.tacticalNotices.value[0].type.toLowerCase().replace(/_/g, '-')}`"
      >
        <i aria-hidden="true"></i>
        <strong>{{ simulationRuntime.tacticalNotices.value[0].title }}</strong>
        <span>{{ simulationRuntime.tacticalNotices.value[0].threatCode }}</span>
        <b v-if="simulationRuntime.tacticalNotices.value[0].type.endsWith('INTENT_CONFIRMED') && simulationRuntime.tacticalNotices.value[0].confidence">
          置信度 {{ Math.round((simulationRuntime.tacticalNotices.value[0].confidence ?? 0) * 100) }}%
        </b>
      </article>
      </Transition>
    </div>
    <div v-if="simulationRuntime.recovering.value" class="recovery-mask">
      <strong>{{ simulationRuntime.recoveryError.value ? '场景恢复未完成' : '正在恢复仿真场景' }}</strong>
      <span>{{ simulationRuntime.recoveryError.value || '保留当前任务，等待设备位置与镜头同步' }}</span>
      <button v-if="simulationRuntime.recoveryError.value" @click="panel?.reload()">重试恢复</button>
    </div>
  </div>
</template>

<style scoped>
.simulation-runtime-host { position: fixed; overflow: hidden; pointer-events: none; opacity: .001; border-radius: 6px; }
.simulation-runtime-host.active { pointer-events: auto; opacity: 1; }
.simulation-runtime-host :deep(.unity-webgl-panel) { width: 100%; height: 100%; border: 0; border-radius: 0; }
.tactical-notice-stack { position: absolute; z-index: 50; top: 48px; left: 50%; width: min(640px, calc(100% - 32px)); pointer-events: none; transform: translateX(-50%); }
.tactical-notice-stack article { display: flex; min-height: 44px; box-sizing: border-box; padding: 10px 16px; align-items: center; gap: 12px; color: #dffbf7; background: rgba(5,24,33,.96); border: 1px solid rgba(108,228,213,.5); border-left: 3px solid #6ce4d5; border-radius: 5px; box-shadow: 0 4px 16px #0003; }
.tactical-strip-enter-active { transition: opacity 180ms ease, transform 180ms ease; }
.tactical-strip-leave-active { transition: opacity 160ms ease, transform 160ms ease; }
.tactical-strip-enter-from, .tactical-strip-leave-to { opacity: 0; transform: translateY(-6px); }
.tactical-notice-stack article > i { width: 9px; height: 9px; background: #6ce4d5; border-radius: 50%; box-shadow: 0 0 11px rgba(108,228,213,.92); }
.tactical-notice-stack strong { color: #effffd; font-size: 14px; line-height: 1.4; }
.tactical-notice-stack span { margin-left: auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #a7d1cd; font-size: 11px; }
.tactical-notice-stack b { flex-shrink: 0; color: #ffcf72; font-size: 11px; }
@media (max-width: 1100px) { .tactical-notice-stack article { flex-wrap: wrap; gap: 6px 10px; padding: 9px 12px; } .tactical-notice-stack strong { font-size: 12px; } }
@media (prefers-reduced-motion: reduce) { .tactical-strip-enter-active, .tactical-strip-leave-active { transition: none; } }
.tactical-notice-stack .event-attack-intent-confirmed { border-color: rgba(255,188,91,.72); }
.tactical-notice-stack .event-attack-intent-confirmed > i { background: #ffbd63; box-shadow: 0 0 11px rgba(255,189,99,.95); }
.tactical-notice-stack .event-escape-intent-confirmed { border-color: rgba(255,129,121,.72); }
.tactical-notice-stack .event-escape-intent-confirmed > i { background: #ff8179; box-shadow: 0 0 11px rgba(255,129,121,.95); }
.recovery-mask { position: absolute; z-index: 40; inset: 0; display: flex; flex-direction: column; gap: 14px; align-items: center; justify-content: center; background: #06161eee; color: #d9f4f1; }
.recovery-mask span { font-size: 13px; color: #8bbab8; }
.recovery-mask button { padding: 8px 18px; background: #153438; border: 1px solid #65dfd0; color: #b9fff4; cursor: pointer; }
</style>
