<script setup lang="ts">
import { Activity, Boxes, LogOut, Plane, Radar, RefreshCw, Ship, UserRound } from '@lucide/vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { useMonitoringStore } from '@/stores/monitoring'

withDefaults(defineProps<{
  title: string
  eyebrow: string
  showRefresh?: boolean
}>(), {
  showRefresh: true,
})

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
  <div class="app-shell console-shell">
    <aside class="sidebar console-sidebar">
      <div class="brand console-brand">
        <div class="brand-mark console-brand-mark"><Plane :size="22" /></div>
        <div>
          <strong>UAV-USV</strong>
          <span>协同仿真平台</span>
        </div>
      </div>

      <nav class="navigation console-navigation" aria-label="主导航">
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

      <div class="sidebar-footer console-sidebar-footer">海空协同任务控制台</div>
    </aside>

    <main class="workspace console-workspace">
      <header class="topbar console-topbar">
        <div class="console-title">
          <p class="eyebrow">{{ eyebrow }}</p>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-actions console-topbar-actions">
          <slot name="actions" />
          <button v-if="showRefresh" class="console-icon-button" type="button" @click="monitoringStore.refresh({}, true)">
            <RefreshCw :size="16" />
            刷新
          </button>
          <div class="current-user console-current-user">
            <UserRound :size="17" />
            <span>
              <strong>{{ authStore.user?.username || 'admin' }}</strong>
              <small>{{ authStore.user?.role || 'ADMIN' }}</small>
            </span>
          </div>
          <button class="console-icon-button" type="button" :disabled="authStore.loading" @click="logout">
            <LogOut :size="16" />
            退出
          </button>
        </div>
      </header>

      <slot />
    </main>
  </div>
</template>

<style scoped>
.console-shell {
  min-height: 100vh;
  background:
    linear-gradient(rgba(108, 228, 213, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(108, 228, 213, 0.03) 1px, transparent 1px),
    linear-gradient(180deg, #071719, #071113 58%, #060d0f);
  background-size: 42px 42px, 42px 42px, auto;
}

.console-sidebar {
  color: #dff8f4;
  background: rgba(8, 20, 23, 0.98);
  border-right: 1px solid rgba(108, 228, 213, 0.18);
}

.console-brand {
  border-bottom-color: rgba(108, 228, 213, 0.18);
}

.console-brand-mark {
  background: #6ce4d5;
}

.console-navigation :deep(.nav-item) {
  color: #9ebfba;
  font-weight: 800;
}

.console-navigation :deep(.nav-item.active) {
  color: #f2fffd;
  background: rgba(108, 228, 213, 0.13);
  box-shadow: inset 3px 0 #6ce4d5;
}

.console-sidebar-footer {
  color: #6f918c;
  border-top-color: rgba(108, 228, 213, 0.14);
}

.console-workspace {
  color: #e9fffb;
}

.console-topbar {
  align-items: flex-start;
}

.console-title :deep(.eyebrow),
.console-title .eyebrow {
  color: #6ce4d5;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.console-title h1 {
  color: #f3fffd;
  font-size: 34px;
}

.console-topbar-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.console-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 13px;
  color: #dff8f4;
  background: rgba(108, 228, 213, 0.08);
  border: 1px solid rgba(108, 228, 213, 0.24);
  border-radius: 5px;
  cursor: pointer;
}

.console-icon-button:hover:not(:disabled) {
  color: #061113;
  background: #6ce4d5;
  border-color: #6ce4d5;
}

.console-icon-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.console-current-user {
  color: #dff8f4;
  border-right-color: rgba(108, 228, 213, 0.18);
}

.console-current-user small {
  color: #87aaa5;
}

@media (max-width: 860px) {
  .console-topbar {
    flex-direction: column;
  }

  .console-topbar-actions {
    justify-content: flex-start;
  }
}
</style>
