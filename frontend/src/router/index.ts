import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import DashboardView from '@/views/DashboardView.vue'
import DeviceManagementView from '@/views/DeviceManagementView.vue'
import LoginView from '@/views/LoginView.vue'
import MissionWorkspaceView from '@/views/MissionWorkspaceView.vue'
import RadarSituationView from '@/views/RadarHudView.vue'
import VisualSensorView from '@/views/OpticalVisionView.vue'
import VirtualFleetConfigView from '@/views/VirtualFleetConfigView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true } },
    { path: '/devices', name: 'devices', component: DeviceManagementView, meta: { requiresAuth: true } },
    { path: '/situation', name: 'situation', component: MissionWorkspaceView, meta: { requiresAuth: true } },
    { path: '/missions', redirect: '/situation' },
    {
      path: '/missions/:missionId/runs/:runId',
      name: 'mission-run',
      redirect: to => ({
        name: 'situation',
        query: {
          missionId: String(to.params.missionId),
          runId: String(to.params.runId),
          ...(to.query.view ? { view: String(to.query.view) } : {}),
        },
      }),
      meta: { requiresAuth: true },
    },
    { path: '/vision', name: 'optical-vision', component: VisualSensorView, meta: { requiresAuth: true } },
    { path: '/visual-sensors', redirect: '/vision' },
    { path: '/radar', name: 'radar-situation', component: RadarSituationView, meta: { requiresAuth: true } },
    { path: '/virtual-fleet', name: 'virtual-fleet-config', component: VirtualFleetConfigView, meta: { requiresAuth: true } },
    { path: '/monitoring', redirect: '/situation' },
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
