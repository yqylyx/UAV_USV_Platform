import { defineStore } from 'pinia'

import type {
  ControlEventPayload,
  GatewayEnvelope,
  MissionStatusPayload,
  PoseBatchPayload,
} from '@/types/realtime'

type RealtimeConnectionState = 'DISCONNECTED' | 'CONNECTING' | 'CONNECTED'

interface RealtimeState {
  connectionState: RealtimeConnectionState
  lastError: string
  runId: string
  streamSequences: Record<string, number>
  poseBatch: GatewayEnvelope<PoseBatchPayload> | null
  missionStatus: GatewayEnvelope<MissionStatusPayload> | null
  controlEvents: GatewayEnvelope<ControlEventPayload>[]
  commandStatuses: Record<string, string>
  lastEnvelope: GatewayEnvelope | null
}

let socket: WebSocket | null = null
let reconnectTimer: number | null = null
let reconnectAttempts = 0
let reconnectEnabled = false

function reconnectDelay() {
  return Math.min(1000 * 2 ** reconnectAttempts, 15000)
}

function realtimeUrl() {
  const configured = import.meta.env.VITE_REALTIME_WS_URL as string | undefined
  if (configured) return configured
  if (import.meta.env.DEV) return `ws://${window.location.hostname}:8081/api/v1/realtime`
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1/realtime`
}

function streamKey(envelope: GatewayEnvelope) {
  const taskScoped = [
    'telemetry.pose_batch', 'mission.status', 'control.ack', 'control.feedback', 'control.result',
  ].includes(envelope.type)
  return taskScoped
    ? `${envelope.runId ?? 'missing-run'}:${envelope.source}:${envelope.streamId}`
    : `${envelope.source}:${envelope.streamId}`
}

function normalizeEnvelope(value: unknown): GatewayEnvelope | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Partial<GatewayEnvelope>
  const sequence = Number(candidate.sequence)
  if (
    typeof candidate.type !== 'string'
    || typeof candidate.source !== 'string'
    || typeof candidate.streamId !== 'string'
    || !Number.isFinite(sequence)
  ) {
    return null
  }
  return {
    version: String(candidate.version ?? 'v1'),
    type: candidate.type,
    source: candidate.source,
    timestamp: String(candidate.timestamp ?? ''),
    runId: candidate.runId ?? null,
    streamId: candidate.streamId,
    sequence,
    payload: candidate.payload ?? {},
  }
}

export const useRealtimeStore = defineStore('realtime', {
  state: (): RealtimeState => ({
    connectionState: 'DISCONNECTED',
    lastError: '',
    runId: '',
    streamSequences: {},
    poseBatch: null,
    missionStatus: null,
    controlEvents: [],
    commandStatuses: {},
    lastEnvelope: null,
  }),
  getters: {
    connected: state => state.connectionState === 'CONNECTED',
    latestSequence: state => (source: string, streamId: string) =>
      state.streamSequences[`${source}:${streamId}`] ?? 0,
  },
  actions: {
    connect() {
      reconnectEnabled = true
      if (socket && socket.readyState !== WebSocket.CLOSED) return
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      this.connectionState = 'CONNECTING'
      this.lastError = ''
      socket = new WebSocket(realtimeUrl())
      socket.onopen = () => {
        this.connectionState = 'CONNECTED'
        this.lastError = ''
        reconnectAttempts = 0
      }
      socket.onmessage = event => this.ingestMessage(event.data)
      socket.onerror = () => {
        this.lastError = 'Realtime WebSocket connection error'
      }
      socket.onclose = () => {
        this.connectionState = 'DISCONNECTED'
        socket = null
        if (reconnectEnabled && reconnectTimer === null) {
          const delay = reconnectDelay()
          reconnectAttempts += 1
          reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null
            this.connect()
          }, delay)
        }
      }
    },
    disconnect() {
      reconnectEnabled = false
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      socket?.close()
      socket = null
      reconnectAttempts = 0
      this.connectionState = 'DISCONNECTED'
    },
    ingestMessage(raw: unknown) {
      try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
        const envelope = normalizeEnvelope(parsed)
        if (!envelope || !this.acceptSequence(envelope)) return
        this.lastEnvelope = envelope
        this.runId = envelope.runId ?? this.runId
        if (envelope.type === 'telemetry.pose_batch') {
          this.poseBatch = envelope as GatewayEnvelope<PoseBatchPayload>
        } else if (envelope.type === 'mission.status') {
          this.missionStatus = envelope as GatewayEnvelope<MissionStatusPayload>
        } else if (
          envelope.type === 'control.ack'
          || envelope.type === 'control.feedback'
          || envelope.type === 'control.result'
        ) {
          const command = envelope as GatewayEnvelope<ControlEventPayload>
          const commandId = command.payload.commandId
          if (commandId && command.payload.status) {
            this.commandStatuses[commandId] = command.payload.status
          }
          this.controlEvents = [
            command,
            ...this.controlEvents,
          ].slice(0, 50)
        }
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : 'Invalid realtime message'
      }
    },
    acceptSequence(envelope: GatewayEnvelope) {
      const key = streamKey(envelope)
      const previous = this.streamSequences[key] ?? 0
      if (envelope.sequence <= previous) return false
      this.streamSequences[key] = envelope.sequence
      return true
    },
    waitForCommandResult(commandId: string, timeoutMs = 15000): Promise<string> {
      const terminal = new Set(['SUCCEEDED', 'FAILED', 'REJECTED', 'CANCELLED', 'TIMEOUT', 'EXPIRED'])
      return new Promise((resolve) => {
        const startedAt = Date.now()
        const timer = window.setInterval(() => {
          const status = this.commandStatuses[commandId]
          if (status && terminal.has(status)) {
            window.clearInterval(timer)
            resolve(status)
          } else if (Date.now() - startedAt >= timeoutMs) {
            window.clearInterval(timer)
            resolve('TIMEOUT')
          }
        }, 100)
      })
    },
    clear() {
      this.runId = ''
      this.streamSequences = {}
      this.poseBatch = null
      this.missionStatus = null
      this.controlEvents = []
      this.commandStatuses = {}
      this.lastEnvelope = null
      this.lastError = ''
    },
  },
})
