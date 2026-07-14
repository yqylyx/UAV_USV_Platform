import { defineStore } from 'pinia'

import { acknowledgeRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus } from '@/api/runtimeControl'

export interface UnityBridgeMessage {
  type: string
  requestId: string
  timestamp: number
  payload: Record<string, unknown>
}

export interface UnityCommandAckResult {
  requestId: string
  success: boolean
  status: string
  deviceCode: string
  commandType: string
  backendStatus?: RuntimeCommandStatus
}

type PendingCommandAck = {
  resolve: (result: UnityCommandAckResult) => void
  reject: (error: Error) => void
  timer: number
}

const pendingCommandAcks = new Map<string, PendingCommandAck>()

function removePendingCommandAck(requestId: string) {
  const pending = pendingCommandAcks.get(requestId)
  if (!pending) return undefined
  window.clearTimeout(pending.timer)
  pendingCommandAcks.delete(requestId)
  return pending
}

function rejectAllPendingCommandAcks(message: string) {
  for (const [requestId, pending] of pendingCommandAcks) {
    window.clearTimeout(pending.timer)
    pending.reject(new Error(message))
    pendingCommandAcks.delete(requestId)
  }
}

export const useUnityBridgeStore = defineStore('unityBridge', {
  state: () => ({
    connected: false,
    lastMessage: null as UnityBridgeMessage | null,
    lastOutgoing: null as UnityBridgeMessage | null,
    error: '',
    trajectoryVisible: true,
    trajectoryTogglePending: false,
    outbox: [] as UnityBridgeMessage[],
    commandKeys: {} as Record<string, string>,
  }),
  actions: {
    setConnected(connected: boolean) {
      this.connected = connected
      if (connected) this.error = ''
      else rejectAllPendingCommandAcks('Unity WebGL 连接已断开')
    },
    setError(message: string) {
      this.error = message
      this.connected = false
      rejectAllPendingCommandAcks(message)
    },
    noteMessage(message: UnityBridgeMessage) {
      this.lastMessage = message
    },
    noteOutgoing(message: UnityBridgeMessage) {
      this.lastOutgoing = message
    },
    setTrajectoryVisibility(visible: boolean) {
      this.trajectoryVisible = visible
      this.trajectoryTogglePending = false
    },
    setTrajectoryTogglePending(pending: boolean) {
      this.trajectoryTogglePending = pending
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
    sendAndWait(
      type: string,
      payload: Record<string, unknown>,
      commandKey: string,
      timeoutMs = 15000,
    ): Promise<UnityCommandAckResult> {
      const requestId = `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          pendingCommandAcks.delete(requestId)
          delete this.commandKeys[requestId]
          void acknowledgeRuntimeCommand(commandKey, false, `Unity 指令确认超时：${type}`).catch(() => undefined)
          reject(new Error(`Unity 指令确认超时：${type}`))
        }, timeoutMs)
        pendingCommandAcks.set(requestId, { resolve, reject, timer })
        this.commandKeys[requestId] = commandKey
        this.outbox.push({ type, requestId, timestamp: Date.now(), payload })
      })
    },
    sendControlCommandAndWait(
      command: string,
      deviceCode: string,
      commandKey: string,
      timeoutMs = 15000,
    ): Promise<UnityCommandAckResult> {
      return this.sendAndWait('sendControlCommand', { command, deviceCode }, commandKey, timeoutMs)
    },
    peekNext() {
      return this.outbox[0] ?? null
    },
    removeNext() {
      this.outbox.shift()
    },
    async handleCommandAck(requestId: string, payload: Record<string, unknown>) {
      const commandKey = this.commandKeys[requestId]
      if (!commandKey) return undefined
      delete this.commandKeys[requestId]
      const success = payload.success === true
      const detail = String(payload.status ?? (success ? 'Unity 已执行' : 'Unity 执行失败'))
      try {
        const command = await acknowledgeRuntimeCommand(commandKey, success, detail)
        removePendingCommandAck(requestId)?.resolve({
          requestId,
          success: success && command.status === 'ACKNOWLEDGED',
          status: detail,
          deviceCode: String(payload.deviceCode ?? ''),
          commandType: String(payload.commandType ?? ''),
          backendStatus: command.status,
        })
        return command
      } catch (error) {
        const reason = error instanceof Error ? error : new Error('后端未能确认 Unity 指令')
        removePendingCommandAck(requestId)?.reject(reason)
        return undefined
      }
    },
  },
})
