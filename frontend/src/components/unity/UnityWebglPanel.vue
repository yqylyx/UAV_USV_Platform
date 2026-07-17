<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { sendIntegrationHeartbeat } from '@/api/integration'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import type { UnityBridgeMessage, UnityRuntimeScope } from '@/stores/unityBridge'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

const props = withDefaults(
  defineProps<{
    iframeSrc?: string
    runtimeScope?: UnityRuntimeScope
    runtimeInstanceId?: string
    missionId?: number
    runId?: number
  }>(),
  {
    iframeSrc: '/unity/index.html?embedded=1',
    runtimeScope: 'SYSTEM_OVERVIEW',
    runtimeInstanceId: 'overview-unity-01',
  },
)

const emit = defineEmits<{
  unityReady: []
  unityMessage: [message: UnityMessage]
  unityError: [message: string]
  unityCommand: [message: UnityMessage]
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const trajectoryStore = useTrajectoryStore()
const unityBridgeStore = useUnityBridgeStore()
const loading = ref(true)
const ready = ref(false)
const controlsReady = ref(false)
const errorMessage = ref('')
const loadHint = ref('正在加载真实 Unity WebGL 构建包')
const buildStamp = Date.now()

let probeTimer: number | null = null
let heartbeatTimer: number | null = null
let readyEmitted = false
let lastRuntimeReportAt = 0

const iframeUrl = computed(() => {
  const separator = props.iframeSrc.includes('?') ? '&' : '?'
  const params = new URLSearchParams({
    v: String(buildStamp),
    scope: props.runtimeScope,
    instanceId: props.runtimeInstanceId,
  })
  if (props.missionId) params.set('missionId', String(props.missionId))
  return `${props.iframeSrc}${separator}${params.toString()}`
})
const statusText = computed(() => (ready.value ? 'UNITY WEBGL ONLINE' : 'WAITING FOR WEBGL'))

function markReady() {
  loading.value = false
  ready.value = true
  errorMessage.value = ''
  loadHint.value = 'Unity WebGL 已加载'
  unityBridgeStore.setConnectedFor(props.runtimeScope, true)
  void reportHeartbeat('ONLINE', `${props.runtimeScope} Unity WebGL 已连接`)
  flushUnityOutbox()
  if (!readyEmitted) {
    readyEmitted = true
    emit('unityReady')
  }
}

function markError(message: string) {
  loading.value = false
  ready.value = false
  errorMessage.value = message
  unityBridgeStore.setConnectedFor(props.runtimeScope, false)
  unityBridgeStore.setErrorFor(props.runtimeScope, message)
  void reportHeartbeat('FAILED', message)
  emit('unityError', message)
}

function parseUnityMessage(data: unknown): UnityMessage | null {
  if (!data) return null
  if (typeof data === 'string') {
    try {
      return JSON.parse(data) as UnityMessage
    } catch {
      return { type: 'raw', payload: { value: data } }
    }
  }
  if (typeof data === 'object') {
    const candidate = data as { source?: string; message?: UnityMessage; type?: string; payload?: Record<string, unknown> }
    if (candidate.source === 'unity-webgl' && candidate.message) return candidate.message
    if (candidate.type) return { type: candidate.type, payload: candidate.payload }
  }
  return null
}

function handleWindowMessage(event: MessageEvent) {
  if (event.source !== iframeRef.value?.contentWindow) return
  const message = parseUnityMessage(event.data)
  if (!message) return

  if (message.type === 'sceneLoaded' || message.type === 'unityReady') {
    markReady()
  }

  if (message.type === 'unityProgress') {
    const progress = Number(message.payload?.progress ?? 0)
    if (Number.isFinite(progress) && progress > 0) {
      loadHint.value = `Unity WebGL 加载中 ${(progress * 100).toFixed(0)}%`
    }
  }

  if (message.type === 'unityError') {
    markError(String(message.payload?.message ?? 'Unity WebGL 加载失败'))
  }

  if (message.type === 'trajectoryFrame' && message.payload) {
    trajectoryStore.ingestFor(props.runtimeScope, message.payload)
    reportRuntimeSnapshot()
  }

  if (message.type === 'bridgeReady') {
    controlsReady.value = message.payload?.controlsReady === true
    unityBridgeStore.setControlsReadyFor(props.runtimeScope, controlsReady.value)
    reportRuntimeSnapshot(true)
  }

  if (
    (message.type === 'commandAck' || message.type === 'cameraChanged' || message.type === 'trajectoryVisibilityChanged') &&
    message.payload
  ) {
    void unityBridgeStore.handleCommandAckFor(props.runtimeScope, message.requestId ?? '', message.payload)
  }

  unityBridgeStore.noteMessageFor(props.runtimeScope, {
    type: message.type,
    requestId: message.requestId ?? '',
    timestamp: message.timestamp ?? Date.now(),
    payload: message.payload ?? {},
  })

  emit('unityMessage', message)
}

function readFrameStatus() {
  const frameWindow = iframeRef.value?.contentWindow as
    | (Window & { uavUsvUnityInstance?: unknown })
    | null
    | undefined
  const frameDocument = iframeRef.value?.contentDocument
  if (!frameWindow || !frameDocument) return null

  const loadingBar = frameDocument.querySelector('#unity-loading-bar') as HTMLElement | null
  const warningText = frameDocument.querySelector('#unity-warning')?.textContent?.trim() ?? ''
  const loadingHidden = !!loadingBar && frameWindow.getComputedStyle(loadingBar).display === 'none'

  return { frameWindow, warningText, loadingHidden }
}

function startIframeProbe() {
  if (probeTimer !== null) window.clearInterval(probeTimer)
  const startedAt = Date.now()

  probeTimer = window.setInterval(() => {
    const status = readFrameStatus()
    if (!status) return

    if (status.frameWindow.uavUsvUnityInstance || status.loadingHidden) {
      markReady()
      if (probeTimer !== null) {
        window.clearInterval(probeTimer)
        probeTimer = null
      }
      return
    }

    if (status.warningText && /does not support WebGL|WebGL\s*not\s*supported/i.test(status.warningText)) {
      markError('浏览器 WebGL 不可用。请打开 Chrome/Edge 的硬件加速，确认 chrome://gpu 或 edge://gpu 中 WebGL/WebGL2 为 Hardware accelerated。')
      if (probeTimer !== null) {
        window.clearInterval(probeTimer)
        probeTimer = null
      }
      return
    }

    if (status.warningText && /error|failed|exception|abort/i.test(status.warningText)) {
      markError(status.warningText)
      if (probeTimer !== null) {
        window.clearInterval(probeTimer)
        probeTimer = null
      }
      return
    }

    const elapsed = Date.now() - startedAt
    if (elapsed > 120000) {
      loadHint.value = 'Unity WebGL 仍在加载，请继续等待或检查浏览器硬件加速'
    } else if (elapsed > 30000) {
      loadHint.value = 'Unity WebGL 构建包较大，正在继续加载'
    }
  }, 500)
}

function handleIframeLoad() {
  trajectoryStore.clearFor(props.runtimeScope)
  loading.value = true
  ready.value = false
  readyEmitted = false
  controlsReady.value = false
  unityBridgeStore.setControlsReadyFor(props.runtimeScope, false)
  errorMessage.value = ''
  loadHint.value = '正在加载真实 Unity WebGL 构建包'
  startIframeProbe()
}

function createRequestId(type: string) {
  return `${type}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`
}

function postToUnity(type: string, payload: Record<string, unknown> = {}) {
  const message: UnityMessage = {
    type,
    requestId: createRequestId(type),
    timestamp: Date.now(),
    payload,
  }
  unityBridgeStore.noteOutgoingFor(props.runtimeScope, {
    type: message.type,
    requestId: message.requestId ?? '',
    timestamp: message.timestamp ?? Date.now(),
    payload: message.payload ?? {},
  })
  emit('unityCommand', message)
  iframeRef.value?.contentWindow?.postMessage(
    {
      source: 'vue-console',
      runtimeScope: props.runtimeScope,
      runtimeInstanceId: props.runtimeInstanceId,
      message,
    },
    window.location.origin,
  )
  return message.requestId
}

function postEnvelope(message: UnityBridgeMessage) {
  // Pinia stores reactive Proxy instances. Window.postMessage only accepts
  // structured-cloneable values, so send a plain envelope to the WebGL iframe.
  const envelope: UnityBridgeMessage = {
    type: String(message.type),
    requestId: String(message.requestId),
    timestamp: Number(message.timestamp),
    payload: JSON.parse(JSON.stringify(message.payload ?? {})) as Record<string, unknown>,
  }
  unityBridgeStore.noteOutgoingFor(props.runtimeScope, envelope)
  emit('unityCommand', envelope)
  iframeRef.value?.contentWindow?.postMessage(
    {
      source: 'vue-console',
      runtimeScope: props.runtimeScope,
      runtimeInstanceId: props.runtimeInstanceId,
      message: envelope,
    },
    window.location.origin,
  )
}

function flushUnityOutbox() {
  const channel = unityBridgeStore.channels[props.runtimeScope]
  if (!channel.connected || !iframeRef.value?.contentWindow) return
  let message = unityBridgeStore.peekNextFor(props.runtimeScope)
  while (message) {
    try {
      postEnvelope(message)
      unityBridgeStore.removeNextFor(props.runtimeScope)
      message = unityBridgeStore.peekNextFor(props.runtimeScope)
    } catch (error) {
      unityBridgeStore.setErrorFor(
        props.runtimeScope,
        error instanceof Error ? error.message : 'Unity command bridge failed',
      )
      break
    }
  }
}

function selectDevice(deviceCode: string) {
  postToUnity('selectDevice', { deviceCode })
}

function focusDevice(deviceCode: string) {
  postToUnity('focusDevice', { deviceCode })
}

function switchCamera(mode: string) {
  postToUnity('switchCamera', { mode })
}

function toggleTrajectory(visible: boolean) {
  postToUnity('toggleTrajectory', { visible })
}

function sendControlCommand(command: string, deviceCode?: string) {
  postToUnity('sendControlCommand', { command, deviceCode })
}

function sendPoseFrame(payload: Record<string, unknown>) {
  postToUnity('poseFrame', payload)
}

async function reportHeartbeat(
  state: 'ONLINE' | 'RUNNING' | 'STOPPED' | 'OFFLINE' | 'FAILED',
  detail: string,
) {
  try {
    await sendIntegrationHeartbeat({
      componentCode: 'unity-client-01',
      instanceId: props.runtimeInstanceId,
      state,
      detail,
      rosConnectionStatus: 'UNKNOWN',
      runtimeScope: props.runtimeScope,
      missionId: props.missionId,
      runId: props.runId,
      controlsReady: controlsReady.value,
      deviceCodes: trajectoryStore.channels[props.runtimeScope].frame?.agents
        .filter(agent => agent.type === 'UAV' || agent.type === 'USV')
        .map(agent => agent.code.toLowerCase()) ?? [],
      trajectorySequence: trajectoryStore.channels[props.runtimeScope].frame?.sequence,
    })
  } catch {
    // Heartbeat failure must not interrupt the local WebGL runtime.
  }
}

function reportRuntimeSnapshot(force = false) {
  const now = Date.now()
  if (!force && now - lastRuntimeReportAt < 1000) return
  lastRuntimeReportAt = now
  void reportHeartbeat('ONLINE', `${props.runtimeScope} Unity WebGL 运行态同步`)
}

defineExpose({
  postToUnity,
  selectDevice,
  focusDevice,
  switchCamera,
  toggleTrajectory,
  sendControlCommand,
  sendPoseFrame,
})

onMounted(() => {
  window.addEventListener('message', handleWindowMessage)
  heartbeatTimer = window.setInterval(() => {
    const state = unityBridgeStore.channels[props.runtimeScope].connected ? 'ONLINE' : 'OFFLINE'
    void reportHeartbeat(state, `${props.runtimeScope} Unity WebGL 心跳`)
  }, 5000)
})

watch(
  () => [
    unityBridgeStore.channels[props.runtimeScope].connected,
    unityBridgeStore.channels[props.runtimeScope].outbox.length,
  ],
  flushUnityOutbox,
)

onBeforeUnmount(() => {
  unityBridgeStore.setConnectedFor(props.runtimeScope, false)
  void reportHeartbeat('OFFLINE', `${props.runtimeScope} Unity WebGL 已卸载`)
  window.removeEventListener('message', handleWindowMessage)
  if (probeTimer !== null) window.clearInterval(probeTimer)
  if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer)
})
</script>

<template>
  <div class="unity-webgl-panel">
    <iframe
      ref="iframeRef"
      class="unity-webgl-frame"
      :src="iframeUrl"
      title="UAV-USV Unity WebGL"
      allow="fullscreen; autoplay; gamepad; xr-spatial-tracking"
      @load="handleIframeLoad"
    ></iframe>

    <div v-if="loading" class="unity-webgl-overlay">
      <strong>Unity WebGL 加载中</strong>
      <div class="unity-webgl-progress"><i></i></div>
      <span>{{ loadHint }}</span>
    </div>

    <div v-if="errorMessage" class="unity-webgl-overlay error">
      <strong>Unity WebGL 加载失败</strong>
      <p>{{ errorMessage }}</p>
      <small>{{ iframeUrl }}</small>
    </div>

    <div class="unity-webgl-status" :class="ready ? 'ready' : 'pending'">
      <i></i>{{ statusText }}
    </div>
  </div>
</template>
