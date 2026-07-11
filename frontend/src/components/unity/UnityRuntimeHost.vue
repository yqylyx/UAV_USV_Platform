<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'

import UnityWebglPanel from '@/components/unity/UnityWebglPanel.vue'

const route = useRoute()
const frameStyle = reactive<Record<string, string>>({})
let viewport: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null
let animationFrame = 0

function parkRuntime() {
  Object.assign(frameStyle, {
    left: '0px',
    top: '0px',
    width: '2px',
    height: '2px',
  })
}

function alignRuntime() {
  const nextViewport = document.querySelector<HTMLElement>('[data-unity-runtime-viewport]')
  if (nextViewport !== viewport) {
    resizeObserver?.disconnect()
    viewport = nextViewport
    if (viewport) {
      resizeObserver = new ResizeObserver(alignRuntime)
      resizeObserver.observe(viewport)
    }
  }
  if (!viewport || route.name !== 'dashboard') {
    parkRuntime()
    return
  }
  const rect = viewport.getBoundingClientRect()
  Object.assign(frameStyle, {
    left: `${Math.round(rect.left)}px`,
    top: `${Math.round(rect.top)}px`,
    width: `${Math.max(2, Math.round(rect.width))}px`,
    height: `${Math.max(2, Math.round(rect.height))}px`,
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

watch(() => route.fullPath, scheduleAlignment, { immediate: true })

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
    class="global-unity-runtime"
    :class="{ active: route.name === 'dashboard' }"
    :style="frameStyle"
    aria-label="全局常驻 Unity WebGL 运行实例"
  >
    <UnityWebglPanel />
  </div>
</template>

<style scoped>
.global-unity-runtime {
  position: fixed;
  z-index: 20;
  overflow: hidden;
  pointer-events: none;
  opacity: 0.001;
  border-radius: 6px;
  transition: opacity 120ms ease;
}

.global-unity-runtime.active {
  pointer-events: auto;
  opacity: 1;
}

.global-unity-runtime :deep(.unity-webgl-panel) {
  width: 100%;
  height: 100%;
}
</style>
