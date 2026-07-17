import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import DashboardView from '@/views/DashboardView.vue'
import DeviceManagementView from '@/views/DeviceManagementView.vue'
import LoginView from '@/views/LoginView.vue'
import MissionControlView from '@/views/MissionControlView.vue'
import MissionExecutionView from '@/views/MissionExecutionView.vue'
import RuntimeMonitorView from '@/views/RuntimeMonitorView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true } },
    { path: '/devices', name: 'devices', component: DeviceManagementView, meta: { requiresAuth: true } },
    { path: '/missions', name: 'missions', component: MissionControlView, meta: { requiresAuth: true } },
    { path: '/missions/:missionId/runs/:runId', name: 'mission-run', component: MissionExecutionView, meta: { requiresAuth: true } },
    { path: '/monitoring', name: 'monitoring', component: RuntimeMonitorView, meta: { requiresAuth: true } },
    { path: '/login', name: 'login', component: LoginView },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.initialize()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && authStore.isAuthenticated) return { name: 'dashboard' }

  return true
})

export default router
