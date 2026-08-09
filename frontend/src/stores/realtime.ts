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
  lastEnvelope: GatewayEnvelope | null
}

let socket: WebSocket | null = null
let reconnectTimer: number | null = null

function realtimeUrl() {
  const configured = import.meta.env.VITE_REALTIME_WS_URL as string | undefined
  if (configured) return configured
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1/realtime`
}

function streamKey(envelope: GatewayEnvelope) {
  return `${envelope.source}:${envelope.streamId}`
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
    lastEnvelope: null,
  }),
  getters: {
    connected: state => state.connectionState === 'CONNECTED',
    latestSequence: state => (source: string, streamId: string) =>
      state.streamSequences[`${source}:${streamId}`] ?? 0,
  },
  actions: {
    connect() {
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
      }
      socket.onmessage = event => this.ingestMessage(event.data)
      socket.onerror = () => {
        this.lastError = 'Realtime WebSocket connection error'
      }
      socket.onclose = () => {
        this.connectionState = 'DISCONNECTED'
        socket = null
      }
    },
    disconnect() {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      socket?.close()
      socket = null
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
          this.controlEvents = [
            envelope as GatewayEnvelope<ControlEventPayload>,
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
    clear() {
      this.runId = ''
      this.streamSequences = {}
      this.poseBatch = null
      this.missionStatus = null
      this.controlEvents = []
      this.lastEnvelope = null
      this.lastError = ''
    },
  },
})
