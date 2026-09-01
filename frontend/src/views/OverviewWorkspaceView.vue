<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import DashboardView from '@/views/DashboardView.vue'
import VirtualFleetConfigView from '@/views/VirtualFleetConfigView.vue'

const route = useRoute()
const simulationActive = computed(() => route.query.workspace === 'simulation')
const simulationMounted = ref(simulationActive.value)

let prewarmTimer: number | null = null
let settleTimer: number | null = null
let switchGeneration = 0

function finishViewportSwitch(generation: number) {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      if (generation !== switchGeneration) return
      window.dispatchEvent(new Event('resize'))
      window.dispatchEvent(new CustomEvent('unity-runtime-track', {
        detail: { duration: 220 },
      }))
      if (settleTimer !== null) window.clearTimeout(settleTimer)
      settleTimer = window.setTimeout(() => {
        if (generation !== switchGeneration) return
        settleTimer = null
        window.dispatchEvent(new Event('resize'))
        window.dispatchEvent(new CustomEvent('unity-runtime-track', {
          detail: { duration: 120 },
        }))
      }, 140)
    })
  })
}

watch(simulationActive, async (active) => {
  const generation = ++switchGeneration
  if (active) simulationMounted.value = true
  await nextTick()
  finishViewportSwitch(generation)
}, { flush: 'pre' })

onMounted(() => {
  // Warm the isolated virtual-fleet iframe after the overview has settled.
  // It stays mounted afterwards, so switching workspaces never rebuilds Unity.
  if (!simulationMounted.value) {
    prewarmTimer = window.setTimeout(() => {
      prewarmTimer = null
      simulationMounted.value = true
    }, 1200)
  }
  finishViewportSwitch(++switchGeneration)
})

onBeforeUnmount(() => {
  if (prewarmTimer !== null) window.clearTimeout(prewarmTimer)
  if (settleTimer !== null) window.clearTimeout(settleTimer)
})
</script>

<template>
  <div class="overview-workspace-stack" :class="{ 'simulation-active': simulationActive }">
    <section
      class="overview-workspace-pane overview-pane"
      :class="simulationActive ? 'is-inactive' : 'is-active'"
      :aria-hidden="simulationActive"
    >
      <DashboardView />
    </section>

    <section
      v-if="simulationMounted"
      class="overview-workspace-pane simulation-pane"
      :class="simulationActive ? 'is-active' : 'is-inactive'"
      :aria-hidden="!simulationActive"
    >
      <VirtualFleetConfigView />
    </section>
  </div>
</template>

<style scoped>
.overview-workspace-stack {
  position: relative;
  min-width: 0;
  min-height: 100dvh;
  overflow: hidden;
  background: #061113;
  isolation: isolate;
}

.overview-workspace-pane {
  width: 100%;
  min-width: 0;
  min-height: 100dvh;
  backface-visibility: hidden;
  contain: layout paint style;
}

.overview-workspace-pane.is-active {
  position: relative;
  z-index: 2;
  visibility: visible;
  opacity: 1;
  pointer-events: auto;
  transform: translate3d(0, 0, 0);
}

.overview-workspace-pane.is-inactive {
  position: absolute;
  inset: 0;
  z-index: 0;
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
  transform: translate3d(-110%, 0, 0);
}
</style>
