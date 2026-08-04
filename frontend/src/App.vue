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
    :viewport="route.name === 'visual-sensors' ? 'visual-sensors-live' : 'dashboard'"
    runtime-scope="SYSTEM_OVERVIEW"
    runtime-instance-id="overview-unity-01"
    :active="route.name === 'dashboard' || route.name === 'visual-sensors'"
    :layer="route.name === 'visual-sensors' ? 24 : 20"
  />
  <UnityRuntimeHost
    v-if="route.meta.requiresAuth && route.name !== 'visual-sensors'"
    viewport="mission-execution"
    runtime-scope="MISSION_CENTER"
    :runtime-instance-id="unityViewportStore.missionInstanceId"
    :mission-id="unityViewportStore.missionId || undefined"
    :run-id="unityViewportStore.runId || undefined"
    :active="route.name === 'missions' && unityViewportStore.target === 'mission-execution'"
    :layer="95"
  />
  <RouterView v-slot="{ Component }">
    <KeepAlive include="DashboardView,MissionWorkspaceView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>
