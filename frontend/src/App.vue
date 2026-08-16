<script setup lang="ts">
import { computed } from 'vue'
import { RouterView } from 'vue-router'
import { useRoute } from 'vue-router'
import UnityRuntimeHost from '@/components/unity/UnityRuntimeHost.vue'
import { useUnityViewportStore } from '@/stores/unityViewport'

const route = useRoute()
const unityViewportStore = useUnityViewportStore()

const showSystemOverviewUnity = computed(
  () => route.meta.requiresAuth && (route.name === 'dashboard' || route.name === 'optical-vision'),
)
const showMissionCenterUnity = computed(
  () =>
    route.meta.requiresAuth
    && route.name === 'situation'
    && unityViewportStore.target === 'mission-execution',
)
</script>

<template>
  <UnityRuntimeHost
    v-if="showSystemOverviewUnity"
    :viewport="route.name === 'optical-vision' ? 'visual-sensors-live' : 'dashboard'"
    runtime-scope="SYSTEM_OVERVIEW"
    runtime-instance-id="overview-unity-01"
    active
    :layer="route.name === 'optical-vision' ? 3 : 20"
  />
  <UnityRuntimeHost
    v-if="showMissionCenterUnity"
    viewport="mission-execution"
    runtime-scope="MISSION_CENTER"
    :runtime-instance-id="unityViewportStore.missionInstanceId"
    :mission-id="unityViewportStore.missionId || undefined"
    :run-id="unityViewportStore.runId || undefined"
    active
    :layer="95"
  />
  <RouterView v-slot="{ Component }">
    <KeepAlive include="DashboardView,MissionWorkspaceView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>
