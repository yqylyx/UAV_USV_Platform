<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useRoute } from 'vue-router'
import UnityRuntimeHost from '@/components/unity/UnityRuntimeHost.vue'
import { useUnityViewportStore } from '@/stores/unityViewport'

const route = useRoute()
const unityViewportStore = useUnityViewportStore()
</script>

<template>
  <UnityRuntimeHost
    v-if="route.meta.requiresAuth"
    viewport="dashboard"
    runtime-scope="SYSTEM_OVERVIEW"
    runtime-instance-id="overview-unity-01"
    :active="route.name === 'dashboard'"
  />
  <UnityRuntimeHost
    v-if="route.meta.requiresAuth"
    viewport="mission-execution"
    runtime-scope="MISSION_CENTER"
    :runtime-instance-id="unityViewportStore.missionInstanceId"
    :mission-id="unityViewportStore.missionId || undefined"
    :run-id="unityViewportStore.runId || undefined"
    :active="unityViewportStore.target === 'mission-execution'"
    :layer="95"
  />
  <RouterView v-slot="{ Component }">
    <KeepAlive include="DashboardView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>
