<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type UnityMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

const props = withDefaults(
  defineProps<{
    iframeSrc?: string
  }>(),
  {
    iframeSrc: '/unity/index.html?embedded=1',
  },
)

const emit = defineEmits<{
  unityReady: []
  unityMessage: [message: UnityMessage]
  unityError: [message: string]
  unityCommand: [message: UnityMessage]
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const ready = ref(false)
const errorMessage = ref('')
const loadHint = ref('正在加载真实 Unity WebGL 构建包')
const buildStamp = Date.now()

let probeTimer: number | null = null
let readyEmitted = false

const iframeUrl = computed(() => {
  const separator = props.iframeSrc.includes('?') ? '&' : '?'
  return `${props.iframeSrc}${separator}v=${buildStamp}`
})
const statusText = computed(() => (ready.value ? 'UNITY WEBGL ONLINE' : 'WAITING FOR WEBGL'))

function markReady() {
  loading.value = false
  ready.value = true
  errorMessage.value = ''
  loadHint.value = 'Unity WebGL 已加载'
  if (!readyEmitted) {
    readyEmitted = true
    emit('unityReady')
  }
}

function markError(message: string) {
  loading.value = false
  ready.value = false
  errorMessage.value = message
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
  loading.value = true
  ready.value = false
  readyEmitted = false
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
  emit('unityCommand', message)
  iframeRef.value?.contentWindow?.postMessage(
    {
      source: 'vue-console',
      message,
    },
    window.location.origin,
  )
  return message.requestId
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
})

onBeforeUnmount(() => {
  window.removeEventListener('message', handleWindowMessage)
  if (probeTimer !== null) window.clearInterval(probeTimer)
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
