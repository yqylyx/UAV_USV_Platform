<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useRoute } from 'vue-router'
import UnityRuntimeHost from '@/components/unity/UnityRuntimeHost.vue'

const route = useRoute()
</script>

<template>
  <UnityRuntimeHost
    v-if="route.meta.requiresAuth"
    :viewport="route.name === 'optical-vision' ? 'visual-sensors-live' : 'dashboard'"
    runtime-scope="SYSTEM_OVERVIEW"
    runtime-instance-id="overview-unity-01"
    :active="route.name === 'dashboard' || route.name === 'optical-vision'"
    :layer="route.name === 'optical-vision' ? 3 : 20"
  />
  <RouterView v-slot="{ Component }">
    <KeepAlive include="DashboardView,MissionWorkspaceView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>
