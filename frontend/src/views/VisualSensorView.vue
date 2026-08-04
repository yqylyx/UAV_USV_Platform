<script setup lang="ts">
import {
  Camera,
  ChevronLeft,
  Expand,
  Gauge,
  Grid2X2,
  Plane,
  Radio,
  Ship,
  Zap,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ConsoleLayout from '@/components/layout/ConsoleLayout.vue'
import { useRadarSensorStore } from '@/stores/radarSensor'
import { useUnityBridgeStore } from '@/stores/unityBridge'
import { useVisualSensorStore } from '@/stores/visualSensor'
import type { RadarOverview } from '@/types/sensor'
import type { VisualSensor } from '@/types/visualSensor'

const store = useVisualSensorStore()
const radarStore = useRadarSensorStore()
const unityBridgeStore = useUnityBridgeStore()
const activePanel = ref<'vision' | 'radar'>('vision')
const mode = ref<'grid' | 'focus'>('grid')
const quality = ref<'720p' | '1080p'>('720p')
const targetFps = 30
let overviewTimer: number | undefined

const overview = computed(() => store.displayOverview)
const sensors = computed(() => overview.value.sensors)
const stats = computed(() => store.streamStats)
const frameUrls = computed(() => store.channels.SYSTEM_OVERVIEW.frameUrls)
const hasBackendFrames = computed(() => Object.keys(frameUrls.value).length > 0)
const radarOverview = computed<RadarOverview>(() => radarStore.overview ?? {
  connected: false,
  onlineCount: 0,
  totalCount: 0,
  updatedAt: 0,
  obstacleCount: 0,
  detectionCount: 0,
  nearestObstacleRange: null,
  latestTargetId: '',
  items: [],
})
const radarItems = computed(() => radarOverview.value.items.slice(0, 6))
const pointCloudItems = computed(() =>
  radarOverview.value.items
    .filter((item) => item.kind === 'POINTCLOUD' && item.x != null && item.y != null)
    .slice(0, 240),
)
const radarPlotPoints = computed(() => {
  const points = pointCloudItems.value
  if (points.length === 0) return []
  const maxAbs = Math.max(
    1,
    ...points.flatMap((item) => [Math.abs(item.x ?? 0), Math.abs(item.y ?? 0)]),
  )
  const scale = 44 / maxAbs
  return points.map((item) => ({
    id: item.id,
    cx: 50 + (item.y ?? 0) * scale,
    cy: 50 - (item.x ?? 0) * scale,
    range: item.range,
  }))
})
const focusedSensor = computed(() =>
  sensors.value.find((sensor) => sensor.cameraId === overview.value.focusedCameraId)
  ?? sensors.value[0],
)
const focusedFrameUrl = computed(() =>
  focusedSensor.value ? frameUrls.value[focusedSensor.value.cameraId] : '',
)
const activeFps = computed(() => {
  const value = stats.value?.measuredFps ?? 0
  return value > 0 ? value.toFixed(1) : '--'
})
const activeResolution = computed(() => {
  if (!stats.value?.streamWidth || !stats.value?.streamHeight) {
    return quality.value === '1080p' ? '1920×1080' : '1280×720'
  }
  return `${stats.value.streamWidth}×${stats.value.streamHeight}`
})
const streamOnline = computed(() =>
  store.unityBridgeReady && stats.value?.active === true,
)

function statusLabel(sensor: VisualSensor) {
  if (sensor.status === 'ONLINE') return '实时'
  if (sensor.status === 'STALE') return '信号中断'
  return '初始化中'
}

function viewLabel(sensor: VisualSensor) {
  return sensor.viewType === 'DOWN' ? '垂直下视' : '艇艏前视'
}

function formatRadarRange(value: number | null) {
  return value == null ? '-- m' : `${value.toFixed(1)} m`
}

function formatRadarTime(value: number) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

function sendSubscription(cameraId = overview.value.focusedCameraId || 'uav_01') {
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: true,
    focusedCameraId: cameraId,
    displayMode: mode.value,
    quality: quality.value,
    targetFps,
    gpuDirect: true,
    jpegFallback: false,
    thumbnailFps: 0.2,
    focusedFps: 1,
  })
}

function selectSensor(cameraId: string, openFocus = false) {
  if (openFocus) mode.value = 'focus'
  void store.select(cameraId)
  sendSubscription(cameraId)
}

function chooseQuality(next: '720p' | '1080p') {
  if (quality.value === next) return
  quality.value = next
}

onMounted(() => {
  sendSubscription()
  void store.refreshOverview()
  void store.refreshFrames()
  void radarStore.refresh(true)
  overviewTimer = window.setInterval(() => {
    void store.refreshOverview()
    void store.refreshFrames()
    void radarStore.refresh(true)
  }, 2500)
})

watch([mode, quality], () => sendSubscription())

onBeforeUnmount(() => {
  unityBridgeStore.sendFor('SYSTEM_OVERVIEW', 'visualSensorSubscribe', {
    enabled: false,
    focusedCameraId: overview.value.focusedCameraId || 'uav_01',
    displayMode: 'off',
    quality: quality.value,
    targetFps,
    gpuDirect: true,
    jpegFallback: false,
  })
  if (overviewTimer) window.clearInterval(overviewTimer)
  store.disposeFrames()
})
</script>

<template>
  <ConsoleLayout title="视觉感知" eyebrow="VISUAL SENSOR CENTER">
    <template #actions>
      <div class="sensor-status-chip" :class="{ online: streamOnline }">
        <Zap :size="15" />
        {{ streamOnline ? 'GPU 低延迟直出' : 'Unity 视觉连接中' }}
      </div>
      <div class="sensor-status-chip" :class="{ online: overview.onlineCount > 0 }">
        <Camera :size="15" />
        {{ overview.onlineCount }}/{{ overview.totalCount }} 路在线
      </div>
      <div class="sensor-status-chip" :class="{ online: radarOverview.connected }">
        <Radio :size="15" />
        Radar {{ radarOverview.onlineCount }}/{{ radarOverview.totalCount || '--' }}
      </div>
    </template>

    <section class="visual-center">
      <nav class="view-switch panel-switch" role="tablist" aria-label="感知视图">
        <button :class="{ active: activePanel === 'vision' }" type="button" @click="activePanel = 'vision'">
          <Grid2X2 :size="16" /> 视觉感知
        </button>
        <button :class="{ active: activePanel === 'radar' }" type="button" @click="activePanel = 'radar'">
          <Radio :size="16" /> 雷达感知
        </button>
      </nav>

      <header v-show="activePanel === 'vision'" class="visual-toolbar">
        <div class="toolbar-copy">
          <span class="section-kicker">LIVE OPTICAL FEEDS</span>
          <h2>六路设备视觉回传</h2>
          <p>无人机垂直下视与无人艇艇艏前视 · Unity WebGL GPU 零拷贝显示</p>
        </div>

        <div class="toolbar-controls">
          <div class="quality-switch" role="group" aria-label="视频清晰度">
            <span>清晰度</span>
            <button
              :class="{ active: quality === '720p' }"
              type="button"
              @click="chooseQuality('720p')"
            >
              720P
            </button>
            <button
              :class="{ active: quality === '1080p' }"
              type="button"
              @click="chooseQuality('1080p')"
            >
              1080P
            </button>
          </div>
        </div>
      </header>

      <div v-show="activePanel === 'vision'" class="stream-metrics">
        <div>
          <Gauge :size="16" />
          <span>实测帧率</span>
          <strong>{{ activeFps }} FPS</strong>
        </div>
        <div>
          <Camera :size="16" />
          <span>单路分辨率</span>
          <strong>{{ activeResolution }}</strong>
        </div>
        <div>
          <Radio :size="16" />
          <span>渲染耗时</span>
          <strong>{{ stats?.renderMs ? `${stats.renderMs.toFixed(1)} ms` : '-- ms' }}</strong>
        </div>
        <div class="transport">
          <Zap :size="16" />
          <span>传输路径</span>
          <strong>Unity GPU Direct</strong>
        </div>
      </div>

      <div v-if="activePanel === 'vision' && stats?.adaptiveFallback" class="adaptive-notice">
        当前设备无法稳定维持六路 1080P / {{ targetFps }} FPS，已自动切换六路 720P，
        以保持连续画面和低延迟。
      </div>

      <div v-show="activePanel === 'vision'" class="live-layout" :class="mode">
        <div
          class="unity-live-viewport"
          :class="mode"
          :data-unity-runtime-viewport="activePanel === 'vision' ? 'visual-sensors-live' : undefined"
        >
          <div v-if="!store.unityBridgeReady && !hasBackendFrames" class="runtime-placeholder">
            <Radio :size="34" />
            <strong>正在初始化 Unity 六路视觉</strong>
            <span>加载完成后将直接显示设备相机实时画面</span>
          </div>

          <img
            v-if="mode === 'focus' && !streamOnline && focusedFrameUrl"
            class="backend-focus-frame"
            :src="focusedFrameUrl"
            alt="ROS visual sensor frame"
          />

          <div v-if="mode === 'grid'" class="sensor-grid-overlay">
            <button
              v-for="sensor in sensors"
              :key="sensor.cameraId"
              class="sensor-overlay-cell"
              :class="{ selected: sensor.focused }"
              type="button"
              @click="selectSensor(sensor.cameraId, true)"
            >
              <img
                v-if="!streamOnline && frameUrls[sensor.cameraId]"
                class="backend-grid-frame"
                :src="frameUrls[sensor.cameraId]"
                alt="ROS visual sensor frame"
              />
              <span class="cell-header">
                <span class="live-badge" :class="sensor.status.toLowerCase()">
                  <i />{{ statusLabel(sensor) }}
                </span>
              </span>
              <span class="cell-footer">
                <span>{{ activeResolution }} · {{ activeFps }} FPS</span>
                <span>点击聚焦 <Expand :size="12" /></span>
              </span>
            </button>
          </div>

          <div v-else-if="focusedSensor" class="focus-overlay">
            <button type="button" @click="mode = 'grid'">
              <ChevronLeft :size="17" /> 返回六路总览
            </button>
            <span>
              <strong>{{ viewLabel(focusedSensor) }}</strong>
              <small>{{ activeResolution }} · {{ activeFps }} FPS · GPU 直出</small>
            </span>
            <span class="live-badge online"><i />实时</span>
          </div>
        </div>

        <aside v-if="mode === 'focus'" class="camera-selector">
          <header>
            <span>CAMERA CHANNELS</span>
            <h3>视觉通道</h3>
          </header>
          <button
            v-for="sensor in sensors"
            :key="sensor.cameraId"
            :class="{ active: sensor.cameraId === focusedSensor?.cameraId }"
            type="button"
            @click="selectSensor(sensor.cameraId)"
          >
            <span class="selector-icon" :class="sensor.deviceType.toLowerCase()">
              <Plane v-if="sensor.deviceType === 'UAV'" :size="17" />
              <Ship v-else :size="17" />
            </span>
            <span>
              <strong>{{ sensor.deviceCode }}</strong>
              <small>{{ viewLabel(sensor) }}</small>
            </span>
            <i :class="{ online: sensor.status === 'ONLINE' }" />
          </button>
          <footer>
            <span>当前通道</span>
            <strong>{{ focusedSensor?.deviceCode ?? '--' }}</strong>
          </footer>
        </aside>
      </div>

      <section v-show="activePanel === 'radar'" class="radar-panel">
        <header>
          <span>RADAR PERCEPTION</span>
          <strong>Radar / pointcloud summary</strong>
          <i :class="{ online: radarOverview.connected }" />
        </header>
        <div class="radar-metrics">
          <article>
            <span>Online</span>
            <strong>{{ radarOverview.onlineCount }}/{{ radarOverview.totalCount || '--' }}</strong>
          </article>
          <article>
            <span>Nearest obstacle</span>
            <strong>{{ formatRadarRange(radarOverview.nearestObstacleRange) }}</strong>
          </article>
          <article>
            <span>Points</span>
            <strong>{{ radarOverview.detectionCount }}</strong>
          </article>
          <article>
            <span>Latest target</span>
            <strong>{{ radarOverview.latestTargetId || '--' }}</strong>
          </article>
        </div>
        <div class="radar-plot" aria-label="2D pointcloud overview">
          <svg viewBox="0 0 100 100" role="img">
            <circle class="plot-ring" cx="50" cy="50" r="44" />
            <circle class="plot-ring muted" cx="50" cy="50" r="29" />
            <circle class="plot-ring muted" cx="50" cy="50" r="14" />
            <line class="plot-axis" x1="50" y1="6" x2="50" y2="94" />
            <line class="plot-axis" x1="6" y1="50" x2="94" y2="50" />
            <circle class="plot-origin" cx="50" cy="50" r="2.4" />
            <circle
              v-for="point in radarPlotPoints"
              :key="point.id"
              class="plot-point"
              :cx="point.cx"
              :cy="point.cy"
              r="1.35"
            >
              <title>{{ point.id }} {{ formatRadarRange(point.range) }}</title>
            </circle>
          </svg>
          <div v-if="radarPlotPoints.length === 0" class="radar-plot-empty">
            Waiting for pointcloud_frame
          </div>
        </div>
        <div class="radar-table">
          <div class="radar-row head">
            <span>ID</span>
            <span>Type</span>
            <span>Range</span>
            <span>Time</span>
          </div>
          <div v-for="item in radarItems" :key="`${item.deviceId}-${item.kind}-${item.id}`" class="radar-row">
            <span>{{ item.id }}</span>
            <span>{{ item.kind }}</span>
            <span>{{ formatRadarRange(item.range) }}</span>
            <span>{{ formatRadarTime(item.timestampMs) }}</span>
          </div>
          <div v-if="radarItems.length === 0" class="radar-empty">
            Waiting for radar_frame / pointcloud_frame
          </div>
        </div>
      </section>

      <footer v-show="activePanel === 'vision'" class="visual-footnote">
        <span><i :class="{ online: streamOnline }" />{{ overview.gatewayDetail }}</span>
        <span>六路同源实时渲染 · 目标 {{ targetFps }} FPS · 无 JPEG/Base64 帧搬运</span>
      </footer>
    </section>
  </ConsoleLayout>
</template>

<style scoped>
.visual-center {
  width: 100%;
  max-width: 2360px;
  margin: 0 auto 28px;
  padding: 18px;
  border: 1px solid rgba(63, 190, 203, .25);
  border-radius: 12px;
  background: rgba(3, 20, 27, .9);
  box-shadow: 0 18px 45px rgba(0, 0, 0, .16);
}

.visual-toolbar,
.toolbar-controls,
.quality-switch,
.view-switch,
.stream-metrics,
.cell-header,
.cell-footer,
.device-title,
.focus-overlay,
.visual-footnote {
  display: flex;
  align-items: center;
}

.visual-toolbar {
  justify-content: space-between;
  gap: 22px;
  margin-bottom: 14px;
}

.section-kicker,
.camera-selector header span {
  color: #4cd6e9;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .13em;
}

.toolbar-copy h2 {
  margin: 3px 0 0;
  color: #f1fffd;
  font-size: 20px;
}

.toolbar-copy p {
  margin: 5px 0 0;
  color: #769a9b;
  font-size: 12px;
}

.toolbar-controls {
  gap: 10px;
}

.quality-switch,
.view-switch {
  gap: 4px;
  height: 42px;
  padding: 4px;
  border: 1px solid rgba(76, 185, 197, .25);
  border-radius: 7px;
  background: #071a21;
}

.quality-switch > span {
  padding: 0 7px;
  color: #6e9497;
  font-size: 10px;
  font-weight: 800;
}

.quality-switch button,
.view-switch button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 13px;
  color: #86a9ac;
  border: 0;
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
}

.quality-switch button.active,
.view-switch button.active {
  color: #041215;
  background: #65ddcf;
  font-weight: 900;
}

.sensor-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 12px;
  color: #809b9d;
  border: 1px solid rgba(83, 155, 165, .22);
  border-radius: 6px;
  background: rgba(5, 25, 32, .85);
  font-size: 12px;
  font-weight: 800;
}

.sensor-status-chip.online {
  color: #5ee7bc;
}

.stream-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 12px;
  border: 1px solid rgba(72, 145, 155, .2);
  border-radius: 8px;
  background: rgba(5, 24, 31, .82);
}

.stream-metrics > div {
  display: grid;
  grid-template-columns: 22px 1fr;
  grid-template-rows: auto auto;
  align-items: center;
  min-height: 54px;
  padding: 8px 14px;
  color: #55dbe0;
  border-right: 1px solid rgba(72, 145, 155, .16);
}

.stream-metrics > div:last-child {
  border-right: 0;
}

.stream-metrics svg {
  grid-row: 1 / 3;
}

.stream-metrics span {
  color: #668d90;
  font-size: 9px;
}

.stream-metrics strong {
  color: #e7fffb;
  font-size: 12px;
}

.stream-metrics .transport strong {
  color: #62e4bf;
}

.adaptive-notice {
  margin-bottom: 12px;
  padding: 9px 12px;
  color: #ffd783;
  border: 1px solid rgba(255, 195, 72, .35);
  border-radius: 6px;
  background: rgba(255, 181, 41, .08);
  font-size: 11px;
}

.backend-grid-frame,
.backend-focus-frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: .86;
}

.backend-grid-frame {
  z-index: 1;
}

.backend-focus-frame {
  z-index: 10;
}

.radar-panel {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  box-sizing: border-box;
  height: clamp(520px, calc(100dvh - 190px), 980px);
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(76, 185, 197, .24);
  border-radius: 8px;
  background: rgba(5, 24, 31, .82);
}

.radar-panel header,
.radar-metrics,
.radar-row {
  display: grid;
  align-items: center;
}

.radar-panel header {
  grid-template-columns: 1fr auto 9px;
  gap: 12px;
  margin-bottom: 10px;
}

.radar-panel header span {
  color: #4cd6e9;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .13em;
}

.radar-panel header strong {
  color: #dff9f5;
  font-size: 13px;
}

.radar-panel header i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #607b7e;
}

.radar-panel header i.online {
  background: #5ce7b7;
  box-shadow: 0 0 9px rgba(92, 231, 183, .75);
}

.radar-metrics {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.radar-metrics article {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  background: #071a21;
}

.panel-switch {
  width: fit-content;
  margin: 0 auto 14px;
}

.radar-metrics span,
.radar-row span {
  color: #769a9b;
  font-size: 10px;
}

.radar-metrics strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #e7fffb;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.radar-table {
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  overflow: hidden;
}

.radar-plot {
  position: relative;
  min-height: 0;
  margin-bottom: 10px;
  overflow: hidden;
  border: 1px solid rgba(72, 145, 155, .18);
  border-radius: 6px;
  background:
    linear-gradient(rgba(73, 160, 170, .07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 160, 170, .06) 1px, transparent 1px),
    #04161d;
  background-size: 24px 24px;
}

.radar-plot svg {
  width: 100%;
  height: 100%;
}

.plot-ring,
.plot-axis {
  fill: none;
  stroke: rgba(117, 203, 205, .22);
  stroke-width: .5;
}

.plot-ring.muted {
  stroke: rgba(117, 203, 205, .12);
}

.plot-origin {
  fill: #65ddcf;
  filter: drop-shadow(0 0 5px rgba(101, 221, 207, .8));
}

.plot-point {
  fill: #5ce7b7;
  opacity: .82;
}

.radar-plot-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #628487;
  font-size: 11px;
}

.radar-row {
  grid-template-columns: 1.2fr 1fr 1fr 1fr;
  min-height: 32px;
  border-bottom: 1px solid rgba(72, 145, 155, .13);
}

.radar-row:last-child {
  border-bottom: 0;
}

.radar-row span {
  min-width: 0;
  padding: 0 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.radar-row.head {
  background: rgba(76, 185, 197, .08);
}

.radar-row.head span {
  color: #9ec3c3;
  font-weight: 900;
}

.radar-empty {
  padding: 18px;
  color: #628487;
  font-size: 11px;
  text-align: center;
}

.live-layout.focus {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 218px;
  gap: 12px;
}

.unity-live-viewport {
  position: relative;
  overflow: hidden;
  min-width: 0;
  border: 1px solid rgba(75, 188, 199, .34);
  border-radius: 9px;
  background:
    linear-gradient(rgba(73, 160, 170, .06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 160, 170, .05) 1px, transparent 1px),
    #02090d;
  background-size: 28px 28px;
}

.unity-live-viewport.grid {
  aspect-ratio: 8 / 3;
}

.unity-live-viewport.focus {
  aspect-ratio: 16 / 9;
}

@media (min-width: 861px) {
  .unity-live-viewport.grid,
  .unity-live-viewport.focus {
    height: clamp(540px, calc(100dvh - 290px), 900px);
    min-height: 0;
    aspect-ratio: auto;
  }
}

@media (min-width: 1920px) and (min-height: 1000px) {
  .visual-center {
    padding: clamp(18px, 1.1vw, 26px);
  }

  .unity-live-viewport.grid,
  .unity-live-viewport.focus {
    height: clamp(680px, calc(100dvh - 300px), 980px);
  }
}

.runtime-placeholder {
  position: absolute;
  inset: 0;
  z-index: 42;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  color: #4fcfd3;
  background: #041219;
}

.runtime-placeholder strong {
  color: #bfe8e5;
  font-size: 13px;
}

.runtime-placeholder span {
  color: #608a8c;
  font-size: 10px;
}

.sensor-grid-overlay {
  position: absolute;
  inset: 4px;
  z-index: 40;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 4px;
  pointer-events: none;
}

.sensor-overlay-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
  padding: 0;
  overflow: hidden;
  color: inherit;
  text-align: left;
  border: 1px solid rgba(105, 211, 212, .2);
  border-radius: 3px;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
  transition: border-color 140ms ease, box-shadow 140ms ease;
}

.sensor-overlay-cell:hover,
.sensor-overlay-cell.selected {
  border-color: rgba(102, 229, 215, .8);
  box-shadow: inset 0 0 0 1px rgba(102, 229, 215, .16);
}

.cell-header,
.cell-footer {
  position: relative;
  z-index: 2;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  background: linear-gradient(180deg, rgba(1, 13, 18, .9), rgba(1, 13, 18, .66));
  backdrop-filter: blur(3px);
}

.cell-header {
  justify-content: flex-end;
  background: transparent;
  backdrop-filter: none;
}

.cell-header .live-badge {
  padding: 4px 7px;
  border: 1px solid rgba(92, 231, 183, .2);
  border-radius: 999px;
  background: rgba(1, 13, 18, .72);
}

.cell-footer {
  color: #97b7b8;
  background: linear-gradient(0deg, rgba(1, 13, 18, .92), rgba(1, 13, 18, .62));
  font-size: 9px;
}

.cell-footer > span:last-child {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #66dcd4;
}

.device-title {
  gap: 7px;
}

.device-title strong,
.device-title small {
  display: block;
}

.device-title strong {
  color: #f0fffc;
  font-size: 12px;
}

.device-title small {
  margin-top: 1px;
  color: #82a4a5;
  font-size: 9px;
}

.device-icon,
.selector-icon {
  display: grid;
  place-items: center;
  border: 1px solid;
  border-radius: 5px;
}

.device-icon {
  width: 28px;
  height: 28px;
}

.uav {
  color: #ffc838;
  border-color: rgba(255, 200, 56, .45);
  background: rgba(255, 200, 56, .1);
}

.usv {
  color: #ff6662;
  border-color: rgba(255, 102, 98, .45);
  background: rgba(255, 102, 98, .1);
}

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #789597;
  font-size: 9px;
  font-weight: 800;
}

.live-badge i,
.visual-footnote i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #647b7e;
}

.live-badge.online {
  color: #5ce7b7;
}

.live-badge.online i,
.visual-footnote i.online {
  background: #5ce7b7;
  box-shadow: 0 0 9px rgba(92, 231, 183, .75);
}

.focus-overlay {
  position: absolute;
  top: 10px;
  right: 10px;
  left: 10px;
  z-index: 40;
  justify-content: space-between;
  gap: 12px;
  min-height: 46px;
  padding: 0 12px;
  border: 1px solid rgba(82, 180, 189, .28);
  border-radius: 6px;
  background: rgba(1, 14, 19, .82);
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.focus-overlay button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #9ec3c3;
  border: 0;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
}

.focus-overlay > span:nth-child(2) {
  flex: 1;
}

.focus-overlay strong,
.focus-overlay small {
  display: block;
}

.focus-overlay strong {
  color: #f0fffc;
  font-size: 12px;
}

.focus-overlay small {
  margin-top: 2px;
  color: #709597;
  font-size: 9px;
}

.camera-selector {
  position: relative;
  z-index: 40;
  padding: 12px;
  border: 1px solid rgba(72, 145, 155, .28);
  border-radius: 9px;
  background: #061820;
}

.camera-selector h3 {
  margin: 2px 0 11px;
  color: #dff9f5;
  font-size: 14px;
}

.camera-selector > button {
  display: grid;
  grid-template-columns: 30px 1fr 8px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 52px;
  margin-bottom: 7px;
  padding: 0 9px;
  color: #76989a;
  text-align: left;
  border: 1px solid rgba(68, 131, 140, .2);
  border-radius: 6px;
  background: #071b22;
  cursor: pointer;
}

.camera-selector > button.active {
  color: #65dfd2;
  border-color: rgba(101, 223, 210, .65);
  background: rgba(101, 223, 210, .08);
}

.selector-icon {
  width: 28px;
  height: 28px;
}

.camera-selector strong,
.camera-selector small {
  display: block;
}

.camera-selector strong {
  color: #e8fffc;
  font-size: 11px;
}

.camera-selector small {
  margin-top: 2px;
  color: #5f7e80;
  font-size: 9px;
}

.camera-selector > button > i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #566e70;
}

.camera-selector > button > i.online {
  background: #5ce7b7;
}

.camera-selector footer {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  color: #6e9294;
  border-top: 1px solid rgba(75, 142, 150, .18);
  font-size: 9px;
}

.camera-selector footer strong {
  color: #66dfd4;
  font-size: 10px;
}

.visual-footnote {
  position: relative;
  z-index: 40;
  justify-content: space-between;
  margin-top: 12px;
  color: #628487;
  font-size: 10px;
}

.visual-footnote span:first-child {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

@media (max-width: 1180px) {
  .visual-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .stream-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stream-metrics > div:nth-child(2) {
    border-right: 0;
  }

  .live-layout.focus {
    grid-template-columns: 1fr;
  }

  .camera-selector {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 7px;
  }

  .camera-selector header,
  .camera-selector footer {
    grid-column: 1 / -1;
  }

  .camera-selector > button {
    margin-bottom: 0;
  }
}

@media (max-width: 860px) {
  .visual-center {
    margin-inline: 14px;
  }

  .toolbar-controls {
    align-items: flex-start;
    flex-direction: column;
  }

  .unity-live-viewport.grid {
    min-height: 600px;
    aspect-ratio: auto;
  }

  .sensor-grid-overlay {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: repeat(3, minmax(0, 1fr));
  }
}
</style>
