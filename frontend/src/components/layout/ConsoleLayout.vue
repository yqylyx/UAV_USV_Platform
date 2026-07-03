<script setup lang="ts">
import { Activity, Boxes, LogOut, Plane, Radar, Ship, UserRound } from '@lucide/vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'

defineProps<{
  title: string
  eyebrow: string
}>()

const router = useRouter()
const authStore = useAuthStore()
const monitoringStore = useMonitoringStore()

async function logout() {
  monitoringStore.disconnectEvents()
  await authStore.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Plane :size="22" /></div>
        <div>
          <strong>UAV-USV</strong>
          <span>协同仿真平台</span>
        </div>
      </div>

      <nav class="navigation" aria-label="主导航">
        <RouterLink class="nav-item" active-class="active" exact-active-class="active" to="/">
          <Activity :size="18" />
          系统总览
        </RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/devices">
          <Boxes :size="18" />
          设备管理
        </RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/missions">
          <Ship :size="18" />
          任务控制
        </RouterLink>
        <RouterLink class="nav-item" active-class="active" to="/monitoring">
          <Radar :size="18" />
          运行监控
        </RouterLink>
      </nav>

      <div class="sidebar-footer">海空协同任务控制台</div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ eyebrow }}</p>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-actions">
          <slot name="actions" />
          <div class="current-user">
            <UserRound :size="17" />
            <span>
              <strong>{{ authStore.user?.username }}</strong>
              <small>{{ authStore.user?.role }}</small>
            </span>
          </div>
          <el-button :icon="LogOut" :loading="authStore.loading" @click="logout">退出</el-button>
        </div>
      </header>

      <slot />
    </main>
  </div>
</template>
