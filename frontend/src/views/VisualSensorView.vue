<script setup lang="ts">
import { Camera, ChevronLeft, Expand, Grid2X2, Plane, Radio, Ship, WifiOff } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useVisualSensorStore } from '@/stores/visualSensor'
import type { VisualSensor } from '@/types/visualSensor'

const store = useVisualSensorStore()
const unityBridgeStore = useUnityBridgeStore()
const mode = ref<'grid' | 'focus'>('grid')
let overviewTimer: number | undefined
let frameTimer: number | undefined

const overview = computed(() => store.displayOverview)
const sensors = computed(() => overview.value.sensors)
const focusedSensor = computed(() =>
  sensors.value.find((sensor) => sensor.cameraId === overview.value.focusedCameraId)
  ?? sensors.value[0],
)

function statusLabel(sensor: VisualSensor) {
  if (sensor.status === 'ONLINE') return '实时'
  if (sensor.status === 'STALE') return '信号中断'
  return '初始化中'
}

function viewLabel(sensor: VisualSensor) {
  return sensor.viewType === 'DOWN' ? '垂直下视' : '艇艏前视'
}

function metric(sensor: VisualSensor) {
  if (sensor.status !== 'ONLINE') return 'Unity 相机初始化中'
  const resolution = sensor.width > 0 ? `${sensor.width}×${sensor.height}` : 'JPEG'
  return `${resolution} · ${sensor.fps.toFixed(1)} FPS · ${sensor.latencyMs} ms`
}

function selectSensor(cameraId: string, openFocus = false) {
  void store.select(cameraId)
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: true,
    focusedCameraId: cameraId,
    thumbnailFps: 1,
    focusedFps: mode.value === 'focus' || openFocus ? 4 : 1,
  })
  if (openFocus) mode.value = 'focus'
  void store.refreshFrames(true)
}

onMounted(() => {
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: true,
    focusedCameraId: overview.value.focusedCameraId || 'uav_01',
    thumbnailFps: 1,
    focusedFps: 1,
  })
  void store.refreshOverview()
  void store.refreshFrames()
  overviewTimer = window.setInterval(() => store.refreshOverview(), 1500)
  frameTimer = window.setInterval(
    () => store.refreshFrames(mode.value === 'focus'),
    700,
  )
})

watch(mode, (nextMode) => {
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: true,
    focusedCameraId: overview.value.focusedCameraId || 'uav_01',
    thumbnailFps: 1,
    focusedFps: nextMode === 'focus' ? 4 : 1,
  })
})

onBeforeUnmount(() => {
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: false,
    focusedCameraId: overview.value.focusedCameraId || 'uav_01',
    thumbnailFps: 1,
    focusedFps: 4,
  })
  if (overviewTimer) window.clearInterval(overviewTimer)
  if (frameTimer) window.clearInterval(frameTimer)
  store.disposeFrames()
})
</script>

<template>
  <ConsoleLayout title="视觉感知" eyebrow="VISUAL SENSOR CENTER">
    <template #actions>
      <div class="sensor-status-chip" :class="{ online: overview.gatewayConnected }">
        <Radio :size="15" />
        {{ store.unityBridgeReady ? 'Unity 视觉在线' : overview.gatewayConnected ? '备用视频在线' : 'Unity 视觉连接中' }}
      </div>
      <div class="sensor-status-chip" :class="{ online: overview.onlineCount > 0 }">
        <Camera :size="15" />
        {{ overview.onlineCount }}/{{ overview.totalCount }} 传感器
      </div>
    </template>

    <section class="visual-center">
      <header class="visual-toolbar">
        <div>
          <h2>设备视觉回传</h2>
          <p>无人机下视与无人艇前视画面 · 当前 Unity WebGL 六路设备相机</p>
        </div>
        <div class="view-switch" role="tablist" aria-label="视觉布局">
          <button :class="{ active: mode === 'grid' }" type="button" @click="mode = 'grid'">
            <Grid2X2 :size="16" /> 六路总览
          </button>
          <button :class="{ active: mode === 'focus' }" type="button" @click="mode = 'focus'">
            <Expand :size="16" /> 单路聚焦
          </button>
        </div>
      </header>

      <div v-if="store.error" class="sensor-alert">{{ store.error }}</div>

      <div v-if="mode === 'grid'" class="sensor-grid">
        <article
          v-for="sensor in sensors"
          :key="sensor.cameraId"
          class="sensor-card"
          :class="{ selected: sensor.focused, live: sensor.status === 'ONLINE' }"
          @click="selectSensor(sensor.cameraId)"
          @dblclick="selectSensor(sensor.cameraId, true)"
        >
          <header>
            <div class="device-title">
              <span class="device-icon" :class="sensor.deviceType.toLowerCase()">
                <Plane v-if="sensor.deviceType === 'UAV'" :size="19" />
                <Ship v-else :size="19" />
              </span>
              <div>
                <strong>{{ sensor.deviceCode }}</strong>
                <small>{{ viewLabel(sensor) }}</small>
              </div>
            </div>
            <span class="live-badge" :class="sensor.status.toLowerCase()">
              <i />{{ statusLabel(sensor) }}
            </span>
          </header>

          <div class="video-frame">
            <img
              v-if="store.frameUrls[sensor.cameraId]"
              :src="store.frameUrls[sensor.cameraId]"
              :alt="`${sensor.deviceCode} ${viewLabel(sensor)}`"
            />
            <div v-else class="signal-placeholder">
              <WifiOff :size="30" />
              <strong>正在连接 Unity 设备相机</strong>
              <span>{{ sensor.cameraId }} · Unity WebGL</span>
            </div>
            <div class="camera-label">{{ sensor.displayName }}</div>
          </div>

          <footer>
            <span>{{ metric(sensor) }}</span>
            <button type="button" @click.stop="selectSensor(sensor.cameraId, true)">
              聚焦查看 <Expand :size="13" />
            </button>
          </footer>
        </article>
      </div>

      <div v-else-if="focusedSensor" class="focus-layout">
        <section class="focus-viewer">
          <header>
            <button type="button" @click="mode = 'grid'">
              <ChevronLeft :size="17" /> 返回六路总览
            </button>
            <div>
              <strong>{{ focusedSensor.displayName }}</strong>
              <span>{{ metric(focusedSensor) }}</span>
            </div>
            <span class="live-badge" :class="focusedSensor.status.toLowerCase()">
              <i />{{ statusLabel(focusedSensor) }}
            </span>
          </header>
          <div class="focus-frame">
            <img
              v-if="store.frameUrls[focusedSensor.cameraId]"
              :src="store.frameUrls[focusedSensor.cameraId]"
              :alt="focusedSensor.displayName"
            />
            <div v-else class="signal-placeholder">
              <WifiOff :size="42" />
              <strong>正在获取 {{ focusedSensor.deviceCode }} 的 Unity 视角</strong>
              <span>Unity WebGL 加载完成后将自动显示该设备相机</span>
            </div>
          </div>
        </section>
        <aside class="camera-selector">
          <h3>视觉通道</h3>
          <button
            v-for="sensor in sensors"
            :key="sensor.cameraId"
            :class="{ active: sensor.cameraId === focusedSensor.cameraId }"
            type="button"
            @click="selectSensor(sensor.cameraId)"
          >
            <Plane v-if="sensor.deviceType === 'UAV'" :size="17" />
            <Ship v-else :size="17" />
            <span><strong>{{ sensor.deviceCode }}</strong><small>{{ viewLabel(sensor) }}</small></span>
            <i :class="{ online: sensor.status === 'ONLINE' }" />
          </button>
        </aside>
      </div>

      <footer class="visual-footnote">
        <span><i :class="{ online: overview.gatewayConnected }" />{{ overview.gatewayDetail }}</span>
        <span>当前高码率通道：{{ focusedSensor?.displayName ?? '--' }}</span>
      </footer>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.visual-center{margin:0 24px 28px;padding:18px;border:1px solid rgba(63,190,203,.25);border-radius:12px;background:rgba(3,20,27,.84);box-shadow:0 18px 45px rgba(0,0,0,.16)}
.visual-toolbar,.view-switch,.device-title,.sensor-card>header,.sensor-card>footer,.focus-viewer>header,.visual-footnote{display:flex;align-items:center}.visual-toolbar{justify-content:space-between;gap:20px;margin-bottom:16px}.visual-toolbar h2{margin:0;color:#f1fffd;font-size:20px}.visual-toolbar p{margin:5px 0 0;color:#769a9b;font-size:12px}
.view-switch{gap:6px;padding:4px;border:1px solid rgba(76,185,197,.25);border-radius:7px;background:#071a21}.view-switch button,.focus-viewer header button,.sensor-card footer button{display:inline-flex;align-items:center;gap:6px;color:#86a9ac;border:0;background:transparent;cursor:pointer}.view-switch button{height:32px;padding:0 13px;border-radius:5px}.view-switch button.active{color:#041215;background:#65ddcf;font-weight:800}
.sensor-status-chip{display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 12px;color:#809b9d;border:1px solid rgba(83,155,165,.22);border-radius:6px;background:rgba(5,25,32,.85);font-size:12px;font-weight:800}.sensor-status-chip.online{color:#5ee7bc}.sensor-alert{margin-bottom:14px;padding:10px 12px;color:#ffaaa8;border:1px solid rgba(255,93,91,.35);border-radius:6px;background:rgba(255,67,67,.08)}
.sensor-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.sensor-card{min-width:0;overflow:hidden;border:1px solid rgba(72,145,155,.25);border-radius:9px;background:#061820;cursor:pointer;transition:border-color 160ms ease,transform 160ms ease}.sensor-card:hover,.sensor-card.selected{border-color:rgba(91,222,209,.72);transform:translateY(-1px)}.sensor-card>header{justify-content:space-between;padding:10px 12px}.device-title{gap:9px}.device-title strong,.device-title small{display:block}.device-title strong{color:#eafffb;font-size:14px}.device-title small{margin-top:2px;color:#769496;font-size:10px}
.device-icon{display:grid;width:32px;height:32px;place-items:center;border:1px solid;border-radius:6px}.device-icon.uav{color:#ffc838;border-color:rgba(255,200,56,.45);background:rgba(255,200,56,.08)}.device-icon.usv{color:#ff6662;border-color:rgba(255,102,98,.45);background:rgba(255,102,98,.08)}
.live-badge{display:inline-flex;align-items:center;gap:5px;color:#789597;font-size:10px;font-weight:800}.live-badge i,.visual-footnote i{width:7px;height:7px;border-radius:50%;background:#647b7e}.live-badge.online{color:#5ce7b7}.live-badge.online i,.visual-footnote i.online{background:#5ce7b7;box-shadow:0 0 9px rgba(92,231,183,.75)}.live-badge.stale{color:#ffc45d}.live-badge.stale i{background:#ffc45d}
.video-frame,.focus-frame{position:relative;overflow:hidden;background:linear-gradient(rgba(73,160,170,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(73,160,170,.07) 1px,transparent 1px),#041219;background-size:28px 28px}.video-frame{aspect-ratio:16/8.8}.focus-frame{min-height:590px}.video-frame img,.focus-frame img{width:100%;height:100%;object-fit:cover}.signal-placeholder{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:7px;color:#4f7478;text-align:center}.signal-placeholder strong{color:#71989b;font-size:12px}.signal-placeholder span{color:#47686b;font-size:10px}.camera-label{position:absolute;left:9px;bottom:8px;padding:4px 7px;color:#d8f7f4;border:1px solid rgba(81,218,206,.24);border-radius:4px;background:rgba(2,15,20,.78);font-size:10px}
.sensor-card>footer{justify-content:space-between;gap:8px;padding:9px 11px;color:#668b8d;font-size:10px}.sensor-card footer button{color:#72dcd2;font-size:10px}.focus-layout{display:grid;grid-template-columns:minmax(0,1fr) 218px;gap:12px}.focus-viewer,.camera-selector{border:1px solid rgba(72,145,155,.28);border-radius:9px;background:#061820}.focus-viewer{overflow:hidden}.focus-viewer>header{justify-content:space-between;gap:16px;min-height:58px;padding:0 14px}.focus-viewer header>div{flex:1}.focus-viewer header strong{display:block;color:#ecfffc;font-size:14px}.focus-viewer header span{color:#668c8f;font-size:10px}.focus-viewer header button{color:#8eb2b4;padding:0}
.camera-selector{padding:13px}.camera-selector h3{margin:0 0 11px;color:#dff9f5;font-size:13px}.camera-selector button{display:grid;grid-template-columns:24px 1fr 8px;align-items:center;gap:7px;width:100%;min-height:54px;margin-bottom:7px;padding:0 10px;color:#76989a;text-align:left;border:1px solid rgba(68,131,140,.2);border-radius:6px;background:#071b22;cursor:pointer}.camera-selector button.active{color:#65dfd2;border-color:rgba(101,223,210,.65);background:rgba(101,223,210,.08)}.camera-selector strong,.camera-selector small{display:block}.camera-selector small{margin-top:2px;color:#5f7e80;font-size:9px}.camera-selector button>i{width:6px;height:6px;border-radius:50%;background:#566e70}.camera-selector button>i.online{background:#5ce7b7}
.visual-footnote{justify-content:space-between;margin-top:12px;color:#628487;font-size:10px}.visual-footnote span:first-child{display:inline-flex;align-items:center;gap:7px}
@media(max-width:1250px){.sensor-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:900px){.visual-center{margin-inline:14px}.sensor-grid{grid-template-columns:1fr}.focus-layout{grid-template-columns:1fr}.focus-frame{min-height:420px}}
</style>
