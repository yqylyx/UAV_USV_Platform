import { defineStore } from 'pinia'

import { acknowledgeRuntimeCommand } from '@/api/runtimeControl'
import type { RuntimeCommandStatus } from '@/api/runtimeControl'

export type UnityRuntimeScope = 'SYSTEM_OVERVIEW' | 'MISSION_CENTER'

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

interface UnityBridgeChannel {
  connected: boolean
  controlsReady: boolean
  lastMessage: UnityBridgeMessage | null
  lastOutgoing: UnityBridgeMessage | null
  error: string
  trajectoryVisible: boolean
  trajectoryTogglePending: boolean
  outbox: UnityBridgeMessage[]
  commandKeys: Record<string, string>
}

type PendingCommandAck = {
  resolve: (result: UnityCommandAckResult) => void
  reject: (error: Error) => void
  timer: number
}

const pendingCommandAcks = new Map<string, PendingCommandAck>()

function createChannel(): UnityBridgeChannel {
  return {
    connected: false,
    controlsReady: false,
    lastMessage: null,
    lastOutgoing: null,
    error: '',
    trajectoryVisible: true,
    trajectoryTogglePending: false,
    outbox: [],
    commandKeys: {},
  }
}

function pendingKey(scope: UnityRuntimeScope, requestId: string) {
  return `${scope}:${requestId}`
}

function removePendingCommandAck(scope: UnityRuntimeScope, requestId: string) {
  const key = pendingKey(scope, requestId)
  const pending = pendingCommandAcks.get(key)
  if (!pending) return undefined
  window.clearTimeout(pending.timer)
  pendingCommandAcks.delete(key)
  return pending
}

function rejectPendingCommandAcks(scope: UnityRuntimeScope, message: string) {
  const prefix = `${scope}:`
  for (const [key, pending] of pendingCommandAcks) {
    if (!key.startsWith(prefix)) continue
    window.clearTimeout(pending.timer)
    pending.reject(new Error(message))
    pendingCommandAcks.delete(key)
  }
}

export const useUnityBridgeStore = defineStore('unityBridge', {
  state: () => ({
    channels: {
      SYSTEM_OVERVIEW: createChannel(),
      MISSION_CENTER: createChannel(),
    } as Record<UnityRuntimeScope, UnityBridgeChannel>,
  }),
  getters: {
    connected: (state) => state.channels.SYSTEM_OVERVIEW.connected,
    lastMessage: (state) => state.channels.SYSTEM_OVERVIEW.lastMessage,
    lastOutgoing: (state) => state.channels.SYSTEM_OVERVIEW.lastOutgoing,
    error: (state) => state.channels.SYSTEM_OVERVIEW.error,
    trajectoryVisible: (state) => state.channels.SYSTEM_OVERVIEW.trajectoryVisible,
    trajectoryTogglePending: (state) => state.channels.SYSTEM_OVERVIEW.trajectoryTogglePending,
    outbox: (state) => state.channels.SYSTEM_OVERVIEW.outbox,
    channel: (state) => (scope: UnityRuntimeScope) => state.channels[scope],
  },
  actions: {
    setConnectedFor(scope: UnityRuntimeScope, connected: boolean) {
      const channel = this.channels[scope]
      channel.connected = connected
      if (connected) channel.error = ''
      else {
        channel.controlsReady = false
        rejectPendingCommandAcks(scope, 'Unity WebGL 连接已断开')
      }
    },
    setConnected(connected: boolean) {
      this.setConnectedFor('SYSTEM_OVERVIEW', connected)
    },
    setErrorFor(scope: UnityRuntimeScope, message: string) {
      const channel = this.channels[scope]
      channel.error = message
      channel.connected = false
      channel.controlsReady = false
      rejectPendingCommandAcks(scope, message)
    },
    setControlsReadyFor(scope: UnityRuntimeScope, ready: boolean) {
      this.channels[scope].controlsReady = ready
    },
    setError(message: string) {
      this.setErrorFor('SYSTEM_OVERVIEW', message)
    },
    noteMessageFor(scope: UnityRuntimeScope, message: UnityBridgeMessage) {
      this.channels[scope].lastMessage = message
    },
    noteMessage(message: UnityBridgeMessage) {
      this.noteMessageFor('SYSTEM_OVERVIEW', message)
    },
    noteOutgoingFor(scope: UnityRuntimeScope, message: UnityBridgeMessage) {
      this.channels[scope].lastOutgoing = message
    },
    noteOutgoing(message: UnityBridgeMessage) {
      this.noteOutgoingFor('SYSTEM_OVERVIEW', message)
    },
    setTrajectoryVisibilityFor(scope: UnityRuntimeScope, visible: boolean) {
      const channel = this.channels[scope]
      channel.trajectoryVisible = visible
      channel.trajectoryTogglePending = false
    },
    setTrajectoryVisibility(visible: boolean) {
      this.setTrajectoryVisibilityFor('SYSTEM_OVERVIEW', visible)
    },
    setTrajectoryTogglePendingFor(scope: UnityRuntimeScope, pending: boolean) {
      this.channels[scope].trajectoryTogglePending = pending
    },
    setTrajectoryTogglePending(pending: boolean) {
      this.setTrajectoryTogglePendingFor('SYSTEM_OVERVIEW', pending)
    },
    sendFor(
      scope: UnityRuntimeScope,
      type: string,
      payload: Record<string, unknown> = {},
      commandKey = '',
    ) {
      const requestId = `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
      const channel = this.channels[scope]
      if (commandKey) channel.commandKeys[requestId] = commandKey
      channel.outbox.push({ type, requestId, timestamp: Date.now(), payload })
      return requestId
    },
    send(type: string, payload: Record<string, unknown> = {}, commandKey = '') {
      return this.sendFor('SYSTEM_OVERVIEW', type, payload, commandKey)
    },
    sendControlCommand(command: string, deviceCode: string, commandKey: string) {
      return this.sendFor('SYSTEM_OVERVIEW', 'sendControlCommand', { command, deviceCode }, commandKey)
    },
    sendAndWaitFor(
      scope: UnityRuntimeScope,
      type: string,
      payload: Record<string, unknown>,
      commandKey: string,
      timeoutMs = 15000,
    ): Promise<UnityCommandAckResult> {
      const requestId = `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
      const channel = this.channels[scope]
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          pendingCommandAcks.delete(pendingKey(scope, requestId))
          delete channel.commandKeys[requestId]
          void acknowledgeRuntimeCommand(commandKey, false, `Unity 指令确认超时：${type}`).catch(() => undefined)
          reject(new Error(`Unity 指令确认超时：${type}`))
        }, timeoutMs)
        pendingCommandAcks.set(pendingKey(scope, requestId), { resolve, reject, timer })
        channel.commandKeys[requestId] = commandKey
        channel.outbox.push({ type, requestId, timestamp: Date.now(), payload })
      })
    },
    sendAndWait(
      type: string,
      payload: Record<string, unknown>,
      commandKey: string,
      timeoutMs = 15000,
    ) {
      return this.sendAndWaitFor('SYSTEM_OVERVIEW', type, payload, commandKey, timeoutMs)
    },
    sendControlCommandAndWaitFor(
      scope: UnityRuntimeScope,
      command: string,
      deviceCode: string,
      commandKey: string,
      timeoutMs = 15000,
    ) {
      return this.sendAndWaitFor(scope, 'sendControlCommand', { command, deviceCode }, commandKey, timeoutMs)
    },
    sendControlCommandAndWait(
      command: string,
      deviceCode: string,
      commandKey: string,
      timeoutMs = 15000,
    ) {
      return this.sendControlCommandAndWaitFor('SYSTEM_OVERVIEW', command, deviceCode, commandKey, timeoutMs)
    },
    peekNextFor(scope: UnityRuntimeScope) {
      return this.channels[scope].outbox[0] ?? null
    },
    peekNext() {
      return this.peekNextFor('SYSTEM_OVERVIEW')
    },
    removeNextFor(scope: UnityRuntimeScope) {
      this.channels[scope].outbox.shift()
    },
    removeNext() {
      this.removeNextFor('SYSTEM_OVERVIEW')
    },
    async handleCommandAckFor(
      scope: UnityRuntimeScope,
      requestId: string,
      payload: Record<string, unknown>,
    ) {
      const channel = this.channels[scope]
      const commandKey = channel.commandKeys[requestId]
      if (!commandKey) return undefined
      delete channel.commandKeys[requestId]
      const success = payload.success === true
      const detail = String(payload.status ?? (success ? 'Unity 已执行' : 'Unity 执行失败'))
      try {
        const command = await acknowledgeRuntimeCommand(commandKey, success, detail)
        removePendingCommandAck(scope, requestId)?.resolve({
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
        removePendingCommandAck(scope, requestId)?.reject(reason)
        return undefined
      }
    },
    handleCommandAck(requestId: string, payload: Record<string, unknown>) {
      return this.handleCommandAckFor('SYSTEM_OVERVIEW', requestId, payload)
    },
  },
})
