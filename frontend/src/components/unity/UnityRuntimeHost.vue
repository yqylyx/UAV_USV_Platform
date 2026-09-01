<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'
import type { UnityRuntimeScope } from '@/stores/unityBridge'

const props = withDefaults(
  defineProps<{
    viewport: string
    iframeSrc?: string
    runtimeScope?: UnityRuntimeScope
    runtimeInstanceId?: string
    missionId?: number
    runId?: number
    active?: boolean
    layer?: number
  }>(),
  {
    iframeSrc: '/unity-overview/index.html?embedded=1',
    runtimeScope: 'SYSTEM_OVERVIEW',
    runtimeInstanceId: 'overview-unity-01',
    active: true,
    layer: 20,
  },
)

const frameStyle = reactive<Record<string, string>>({})
const runtimePanel = ref<InstanceType<typeof UnityWebglPanel> | null>(null)
let viewportElement: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null
let animationFrame = 0
let alignmentUntil = 0
let viewportSettleTimer: number | null = null
let lastWidth = 1280
let lastHeight = 720

function parkRuntime() {
  // Keep a real render target while the persistent WebGL instance is parked.
  // Collapsing it to 2x2 forced Unity to recreate a low-resolution backbuffer
  // and caused a blurred, stuttering first second when returning to 3-D.
  Object.assign(frameStyle, {
    left: '-10000px',
    top: '0px',
    width: `${lastWidth}px`,
    height: `${lastHeight}px`,
  })
}

function alignRuntime() {
  const nextViewport = props.active
    ? document.querySelector<HTMLElement>(`[data-unity-runtime-viewport="${props.viewport}"]`)
    : null
  if (nextViewport !== viewportElement) {
    resizeObserver?.disconnect()
    viewportElement = nextViewport
    if (viewportElement) {
      resizeObserver = new ResizeObserver(alignRuntime)
      resizeObserver.observe(viewportElement)
    }
  }
  if (!viewportElement || !props.active) {
    parkRuntime()
    return
  }
  const rect = viewportElement.getBoundingClientRect()
  // Active runtime must match the viewport exactly. The previous 640×360
  // minimum made a short camera card render a taller fixed layer, so the
  // Unity canvas leaked out below the card as a visible strip.
  lastWidth = Math.max(1, Math.round(rect.width))
  lastHeight = Math.max(1, Math.round(rect.height))
  Object.assign(frameStyle, {
    left: `${Math.round(rect.left)}px`,
    top: `${Math.round(rect.top)}px`,
    width: `${lastWidth}px`,
    height: `${lastHeight}px`,
  })
}

function scheduleAlignment() {
  window.cancelAnimationFrame(animationFrame)
  void nextTick(() => {
    alignmentUntil = Math.max(alignmentUntil, performance.now() + 100)
    const track = () => {
      alignRuntime()
      if (performance.now() < alignmentUntil) animationFrame = window.requestAnimationFrame(track)
    }
    animationFrame = window.requestAnimationFrame(track)
  })
}

function scheduleViewportSettle(delay = 180) {
  if (viewportSettleTimer !== null) window.clearTimeout(viewportSettleTimer)
  viewportSettleTimer = window.setTimeout(() => {
    viewportSettleTimer = null
    if (!props.active) return
    alignRuntime()
    runtimePanel.value?.syncViewport()
  }, delay)
}

function trackRuntime(event: Event) {
  const duration = event instanceof CustomEvent
    ? Number(event.detail?.duration ?? 500)
    : 500
  alignmentUntil = Math.max(alignmentUntil, performance.now() + Math.max(100, duration))
  scheduleAlignment()
  scheduleViewportSettle(Math.max(140, duration + 24))
}

watch(() => [props.viewport, props.active], () => {
  scheduleAlignment()
  scheduleViewportSettle()
}, { immediate: true })

onMounted(() => {
  window.addEventListener('resize', scheduleAlignment)
  window.addEventListener('scroll', alignRuntime, true)
  window.addEventListener('unity-runtime-track', trackRuntime)
  scheduleAlignment()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.cancelAnimationFrame(animationFrame)
  if (viewportSettleTimer !== null) window.clearTimeout(viewportSettleTimer)
  window.removeEventListener('resize', scheduleAlignment)
  window.removeEventListener('scroll', alignRuntime, true)
  window.removeEventListener('unity-runtime-track', trackRuntime)
})
</script>

<template>
  <div
    class="unity-runtime-host"
    :class="{ active }"
    :style="{ ...frameStyle, zIndex: String(layer) }"
    :aria-label="`${runtimeScope} Unity WebGL 运行实例`"
  >
    <UnityWebglPanel
      ref="runtimePanel"
      :iframe-src="iframeSrc"
      :runtime-scope="runtimeScope"
      :runtime-instance-id="runtimeInstanceId"
      :mission-id="missionId"
      :run-id="runId"
    />
  </div>
</template>

<style scoped>
.unity-runtime-host {
  position: fixed;
  overflow: hidden;
  pointer-events: none;
  opacity: 0.001;
  border-radius: 6px;
  transition: opacity 120ms ease;
}

.unity-runtime-host.active {
  pointer-events: auto;
  opacity: 1;
}

.unity-runtime-host :deep(.unity-webgl-panel) {
  width: 100%;
  height: 100%;
}
</style>
