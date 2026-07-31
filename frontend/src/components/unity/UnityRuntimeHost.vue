<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, watch } from 'vue'

import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'
import type { UnityRuntimeScope } from '@/stores/unityBridge'

const props = withDefaults(
  defineProps<{
    viewport: string
    runtimeScope?: UnityRuntimeScope
    runtimeInstanceId?: string
    missionId?: number
    runId?: number
    active?: boolean
    layer?: number
  }>(),
  {
    runtimeScope: 'SYSTEM_OVERVIEW',
    runtimeInstanceId: 'overview-unity-01',
    active: true,
    layer: 20,
  },
)

const frameStyle = reactive<Record<string, string>>({})
let viewportElement: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null
let animationFrame = 0
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
  lastWidth = Math.max(640, Math.round(rect.width))
  lastHeight = Math.max(360, Math.round(rect.height))
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
    animationFrame = window.requestAnimationFrame(() => {
      alignRuntime()
      animationFrame = window.requestAnimationFrame(alignRuntime)
    })
  })
}

watch(() => [props.viewport, props.active], scheduleAlignment, { immediate: true })

onMounted(() => {
  window.addEventListener('resize', scheduleAlignment)
  window.addEventListener('scroll', alignRuntime, true)
  scheduleAlignment()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.cancelAnimationFrame(animationFrame)
  window.removeEventListener('resize', scheduleAlignment)
  window.removeEventListener('scroll', alignRuntime, true)
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
