import { defineStore } from 'pinia'

import { acknowledgeRuntimeCommand } from '@/api/runtimeControl'

export interface UnityBridgeMessage {
  type: string
  requestId: string
  timestamp: number
  payload: Record<string, unknown>
}

export const useUnityBridgeStore = defineStore('unityBridge', {
  state: () => ({
    connected: false,
    lastMessage: null as UnityBridgeMessage | null,
    lastOutgoing: null as UnityBridgeMessage | null,
    error: '',
    outbox: [] as UnityBridgeMessage[],
    commandKeys: {} as Record<string, string>,
  }),
  actions: {
    setConnected(connected: boolean) {
      this.connected = connected
      if (connected) this.error = ''
    },
    setError(message: string) {
      this.error = message
      this.connected = false
    },
    noteMessage(message: UnityBridgeMessage) {
      this.lastMessage = message
    },
    noteOutgoing(message: UnityBridgeMessage) {
      this.lastOutgoing = message
    },
    send(type: string, payload: Record<string, unknown> = {}, commandKey = '') {
      const requestId = `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
      if (commandKey) this.commandKeys[requestId] = commandKey
      this.outbox.push({ type, requestId, timestamp: Date.now(), payload })
      return requestId
    },
    sendControlCommand(command: string, deviceCode: string, commandKey: string) {
      return this.send('sendControlCommand', { command, deviceCode }, commandKey)
    },
    takeNext() {
      return this.outbox.shift() ?? null
    },
    async handleCommandAck(requestId: string, payload: Record<string, unknown>) {
      const commandKey = this.commandKeys[requestId]
      if (!commandKey) return
      delete this.commandKeys[requestId]
      const success = payload.success === true
      const detail = String(payload.status ?? (success ? 'Unity 已执行' : 'Unity 执行失败'))
      await acknowledgeRuntimeCommand(commandKey, success, detail).catch(() => undefined)
    },
  },
})
