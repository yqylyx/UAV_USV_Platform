import { defineStore } from 'pinia'

import {
  fetchCsrfToken,
  fetchCurrentUser,
  login as requestLogin,
  logout as requestLogout,
} from '@/api/auth'
import type { CurrentUser, LoginPayload } from '@/types/auth'

interface AuthState {
  user: CurrentUser | null
  initialized: boolean
  loading: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    initialized: false,
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
  },
  actions: {
    async initialize(force = false) {
      if (this.initialized && !force) return

      try {
        await fetchCsrfToken()
        this.user = await fetchCurrentUser()
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async login(payload: LoginPayload) {
      this.loading = true
      try {
        this.user = await requestLogin(payload)
        this.initialized = true
      } finally {
        this.loading = false
      }
    },
    async logout() {
      this.loading = true
      try {
        await requestLogout()
      } catch {
        // Local logout should still complete if the session already expired
        // or CSRF renewal fails during navigation.
      } finally {
        this.user = null
        this.initialized = true
        this.loading = false
      }
    },
  },
})
