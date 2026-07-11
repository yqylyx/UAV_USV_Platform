<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useRoute } from 'vue-router'
import UnityRuntimeHost from '@/components/unity/UnityRuntimeHost.vue'

const route = useRoute()
</script>

<template>
  <UnityRuntimeHost v-if="route.meta.requiresAuth" />
  <RouterView v-slot="{ Component }">
    <KeepAlive include="DashboardView">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
</template>
