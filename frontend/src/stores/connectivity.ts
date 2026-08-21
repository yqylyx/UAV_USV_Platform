import { defineStore } from 'pinia'

export type BackendConnectionState =
  | 'UNKNOWN'
  | 'ONLINE'
  | 'DEGRADED'
  | 'TIMEOUT'
  | 'OFFLINE'
  | 'AUTH_EXPIRED'

export const useConnectivityStore = defineStore('connectivity', {
  state: () => ({
    backend: 'UNKNOWN' as BackendConnectionState,
    message: '',
    lastSuccessAt: 0,
    lastFailureAt: 0,
  }),
  getters: {
    showBanner: state => ['DEGRADED', 'TIMEOUT', 'OFFLINE'].includes(state.backend),
  },
  actions: {
    markOnline() {
      this.backend = 'ONLINE'
      this.message = ''
      this.lastSuccessAt = Date.now()
    },
    markFailure(state: BackendConnectionState, message: string) {
      this.backend = state
      this.message = message
      this.lastFailureAt = Date.now()
    },
  },
})
