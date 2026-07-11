<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type TrackKind = 'USV' | 'UAV' | 'TARGET'

type Point = {
  x: number
  z: number
}

type TrackDefinition = {
  id: string
  label: string
  shortLabel: string
  kind: TrackKind
  color: string
  angle: number
}

type TrackState = TrackDefinition & {
  position: Point
  history: Point[]
  distance: number
}

type WorldBounds = {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

const props = withDefaults(
  defineProps<{
    missionName?: string
    missionStatus?: string
  }>(),
  {
    missionName: '三机三艇协同围捕预演',
    missionStatus: 'READY',
  },
)

// Exact colors used by ChaseCamera.cs.
const unityColors = {
  usv: '#ff2e24',
  uav: '#ffc71f',
  target: '#1f75ff',
}

const definitions: TrackDefinition[] = [
  { id: 'usv-1', label: 'USV-1', shortLabel: 'S1', kind: 'USV', color: unityColors.usv, angle: 0 },
  { id: 'usv-2', label: 'USV-2', shortLabel: 'S2', kind: 'USV', color: unityColors.usv, angle: 120 },
  { id: 'usv-3', label: 'USV-3', shortLabel: 'S3', kind: 'USV', color: unityColors.usv, angle: 240 },
  { id: 'uav-1', label: 'UAV-1', shortLabel: 'A1', kind: 'UAV', color: unityColors.uav, angle: 60 },
  { id: 'uav-2', label: 'UAV-2', shortLabel: 'A2', kind: 'UAV', color: unityColors.uav, angle: 180 },
  { id: 'uav-3', label: 'UAV-3', shortLabel: 'A3', kind: 'UAV', color: unityColors.uav, angle: 300 },
  { id: 'target', label: 'TARGET', shortLabel: 'T', kind: 'TARGET', color: unityColors.target, angle: 0 },
]

// 900px inset: Unity clamps the statistics column to 185px and leaves 8px margins.
const plotRect = { x: 8, y: 8, width: 699, height: 484 }
const statisticsRect = { x: 715, y: 8, width: 177, height: 484 }
const gridDivisions = [1, 2, 3, 4]
const captureRadius = 18
const defenseRadius = 30
const trajectoryWorldPadding = 8
const trajectorySampleSeconds = 0.2
const trajectoryMinSampleDistance = 0.25
const trajectoryMaxSamplesPerAgent = 900
const trajectoryDrawSegmentsPerAgent = 140

const playing = ref(true)
const elapsed = ref(0)
const tracks = ref<TrackState[]>([])
let animationFrame = 0
let previousFrame = 0
let sampleAccumulator = 0

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
}

function smoothstep(value: number) {
  const t = clamp01(value)
  return t * t * (3 - 2 * t)
}

function lerp(from: number, to: number, t: number) {
  return from + (to - from) * t
}

function distanceBetween(from: Point, to: Point) {
  return Math.hypot(to.x - from.x, to.z - from.z)
}

function polar(centerPoint: Point, angleDegrees: number, radius: number): Point {
  const radians = (angleDegrees * Math.PI) / 180
  return {
    x: centerPoint.x + Math.cos(radians) * radius,
    z: centerPoint.z + Math.sin(radians) * radius,
  }
}

function targetPosition(time: number): Point {
  return {
    x: Math.sin(time * 0.17) * 13 + Math.sin(time * 0.051) * 5,
    z: Math.sin(time * 0.11 + 0.8) * 8 + Math.cos(time * 0.07) * 4,
  }
}

function positionFor(definition: TrackDefinition, time: number): Point {
  const target = targetPosition(time)
  if (definition.kind === 'TARGET') return target

  if (definition.kind === 'USV') {
    const progress = smoothstep(time / 52)
    const radius = lerp(72, captureRadius, progress)
    const angle = definition.angle + Math.sin(time * 0.16 + definition.angle) * 4.5
    return polar(target, angle, radius)
  }

  const progress = smoothstep((time - 5) / 55)
  const radius = lerp(98, defenseRadius, progress)
  const orbit = definition.angle + time * lerp(1.6, 0.25, progress)
  return polar(target, orbit, radius)
}

function buildTracks(time = 0): TrackState[] {
  return definitions.map((definition) => {
    const position = positionFor(definition, time)
    return {
      ...definition,
      position,
      history: [{ ...position }],
      distance: 0,
    }
  })
}

function updateTracks(time: number, sample: boolean) {
  for (const track of tracks.value) {
    const next = positionFor(track, time)
    track.position = next
    if (!sample) continue

    const previous = track.history[track.history.length - 1]
    const moved = previous ? distanceBetween(previous, next) : Number.POSITIVE_INFINITY
    if (moved < trajectoryMinSampleDistance) continue

    if (previous) track.distance += moved
    track.history.push({ ...next })
    if (track.history.length > trajectoryMaxSamplesPerAgent) track.history.shift()
  }
  tracks.value = [...tracks.value]
}

const targetTrack = computed(() => tracks.value.find((track) => track.kind === 'TARGET'))

// Port of TryGetTrajectoryBounds + FitTrajectoryBoundsToPlot.
const worldBounds = computed<WorldBounds>(() => {
  const points = tracks.value.flatMap((track) => [...track.history, track.position])
  const target = targetTrack.value?.position ?? { x: 0, z: 0 }
  points.push(
    { x: target.x - captureRadius, z: target.z - captureRadius },
    { x: target.x + captureRadius, z: target.z + captureRadius },
  )

  let minX = Math.min(...points.map((point) => point.x)) - trajectoryWorldPadding
  let maxX = Math.max(...points.map((point) => point.x)) + trajectoryWorldPadding
  let minZ = Math.min(...points.map((point) => point.z)) - trajectoryWorldPadding
  let maxZ = Math.max(...points.map((point) => point.z)) + trajectoryWorldPadding

  const plotAspect = plotRect.width / plotRect.height
  const width = Math.max(1, maxX - minX)
  const height = Math.max(1, maxZ - minZ)
  if (width / height > plotAspect) {
    const fittedHeight = width / plotAspect
    const extra = (fittedHeight - height) / 2
    minZ -= extra
    maxZ += extra
  } else {
    const fittedWidth = height * plotAspect
    const extra = (fittedWidth - width) / 2
    minX -= extra
    maxX += extra
  }

  return { minX, maxX, minZ, maxZ }
})

function toView(point: Point) {
  const bounds = worldBounds.value
  return {
    x: plotRect.x + ((point.x - bounds.minX) / (bounds.maxX - bounds.minX)) * plotRect.width,
    y: plotRect.y + ((bounds.maxZ - point.z) / (bounds.maxZ - bounds.minZ)) * plotRect.height,
  }
}

function sampledHistory(history: Point[]) {
  if (history.length <= 1) return history
  const stride = Math.max(1, Math.ceil((history.length - 1) / trajectoryDrawSegmentsPerAgent))
  const result: Point[] = []
  for (let index = 0; index < history.length - 1; index += stride) {
    const point = history[index]
    if (point) result.push(point)
  }
  const lastPoint = history[history.length - 1]
  if (lastPoint) result.push(lastPoint)
  return result
}

function toPath(history: Point[]) {
  return sampledHistory(history)
    .map((point, index) => {
      const mapped = toView(point)
      return `${index === 0 ? 'M' : 'L'} ${mapped.x.toFixed(1)} ${mapped.y.toFixed(1)}`
    })
    .join(' ')
}

function headingGeometry(track: TrackState, marker: { x: number; y: number }) {
  let previous = track.history[track.history.length - 1] ?? track.position
  if (distanceBetween(previous, track.position) < 0.001) {
    previous = track.history[track.history.length - 2] ?? previous
  }

  const dx = track.position.x - previous.x
  const dy = -(track.position.z - previous.z)
  const magnitude = Math.hypot(dx, dy)
  if (magnitude < 0.001) {
    return { tip: { x: marker.x + 13, y: marker.y }, wingA: { x: marker.x + 9, y: marker.y + 3 }, wingB: { x: marker.x + 9, y: marker.y - 3 } }
  }

  const x = dx / magnitude
  const y = dy / magnitude
  const tip = { x: marker.x + x * 13, y: marker.y + y * 13 }
  const side = { x: -y, y: x }
  return {
    tip,
    wingA: { x: tip.x - x * 4 + side.x * 3, y: tip.y - y * 4 + side.y * 3 },
    wingB: { x: tip.x - x * 4 - side.x * 3, y: tip.y - y * 4 - side.y * 3 },
  }
}

const viewTracks = computed(() =>
  tracks.value.map((track) => {
    const view = toView(track.position)
    return {
      ...track,
      view,
      path: toPath(track.history),
      heading: headingGeometry(track, view),
    }
  }),
)

function radialFormationReadiness(subject: Point, center: Point, radius: number, tolerance: number) {
  const radialError = Math.abs(distanceBetween(subject, center) - radius)
  return smoothstep(1 - radialError / Math.max(1, tolerance))
}

function arcPath(center: Point, radius: number, startAngle: number, endAngle: number) {
  const segments = Math.max(2, Math.ceil((endAngle - startAngle) * 12))
  const points: Point[] = []
  for (let index = 0; index <= segments; index += 1) {
    const angle = lerp(startAngle, endAngle, index / segments)
    points.push({
      x: center.x + Math.cos(angle) * radius,
      z: center.z + Math.sin(angle) * radius,
    })
  }
  return points
    .map((point, index) => {
      const mapped = toView(point)
      return `${index === 0 ? 'M' : 'L'} ${mapped.x.toFixed(1)} ${mapped.y.toFixed(1)}`
    })
    .join(' ')
}

// Port of DrawUsvEncirclement: each boat grows its own 120-degree arc.
const usvFormationOverlay = computed(() => {
  const center = targetTrack.value?.position ?? { x: 0, z: 0 }
  const boats = tracks.value.filter((track) => track.kind === 'USV')
  const items = boats.map((boat) => {
    const readiness = radialFormationReadiness(boat.position, center, captureRadius, Math.max(14, captureRadius * 1.75))
    const offset = { x: boat.position.x - center.x, z: boat.position.z - center.z }
    const bearing = Math.atan2(offset.z, offset.x)
    const halfArc = (Math.PI / 3) * readiness
    return {
      readiness,
      path: readiness > 0.01 ? arcPath(center, captureRadius, bearing - halfArc, bearing + halfArc) : '',
    }
  })
  const progress = items.length ? items.reduce((sum, item) => sum + item.readiness, 0) / items.length : 0
  return {
    items,
    progress,
    labelPoint: toView({ x: center.x + captureRadius, z: center.z }),
  }
})

// Port of DrawUavTriangle: an edge only grows when both endpoint UAVs are ready.
const uavFormationOverlay = computed(() => {
  const center = targetTrack.value?.position ?? { x: 0, z: 0 }
  const drones = tracks.value.filter((track) => track.kind === 'UAV').slice(0, 3)
  const readiness = drones.map((drone, index) => {
    const airborne = elapsed.value >= 5 + index * 0.75
    return airborne ? radialFormationReadiness(drone.position, center, defenseRadius, Math.max(18, defenseRadius)) : 0
  })
  const edges = drones.map((drone, index) => {
    const nextIndex = (index + 1) % drones.length
    const next = drones[nextIndex] ?? drone
    const edgeProgress = Math.min(readiness[index] ?? 0, readiness[nextIndex] ?? 0)
    const from = toView(drone.position)
    const to = toView(next.position)
    return {
      progress: edgeProgress,
      from,
      to: {
        x: lerp(from.x, to.x, edgeProgress),
        y: lerp(from.y, to.y, edgeProgress),
      },
    }
  })
  const progress = readiness.length ? readiness.reduce((sum, value) => sum + value, 0) / readiness.length : 0
  return {
    edges,
    progress,
    labelPoint: toView({ x: center.x - defenseRadius, z: center.z }),
  }
})

const phase = computed(() => {
  if (elapsed.value < 8) return 'UAV 起飞 / USV 离岸'
  if (elapsed.value < 22) return '目标搜索与接触'
  if (elapsed.value < 52) return '三角编队协同收敛'
  return '合围半径保持'
})

const elapsedLabel = computed(() => {
  const totalSeconds = Math.max(0, Math.floor(elapsed.value))
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
})

function formatDistance(distance: number) {
  return distance >= 1000 ? `${(distance / 1000).toFixed(2)}km` : `${Math.round(distance)}m`
}

function togglePlayback() {
  playing.value = !playing.value
}

function resetSimulation() {
  elapsed.value = 0
  sampleAccumulator = 0
  tracks.value = buildTracks(0)
  playing.value = true
}

function animate(timestamp: number) {
  if (!previousFrame) previousFrame = timestamp
  const delta = Math.min(0.05, (timestamp - previousFrame) / 1000)
  previousFrame = timestamp

  if (playing.value) {
    elapsed.value += delta
    sampleAccumulator += delta
    const shouldSample = sampleAccumulator >= trajectorySampleSeconds
    if (shouldSample) sampleAccumulator = 0
    updateTracks(elapsed.value, shouldSample)
  }

  animationFrame = window.requestAnimationFrame(animate)
}

onMounted(() => {
  tracks.value = buildTracks(0)
  animationFrame = window.requestAnimationFrame(animate)
})

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrame)
})
</script>

<template>
  <section class="trajectory-simulator" data-testid="mission-trajectory-map">
    <header class="trajectory-toolbar">
      <div>
        <span>UNITY TRAJECTORY REPLICA / VUE SVG</span>
        <strong>{{ missionName }}</strong>
        <small>复刻 ChaseCamera 轨迹统计面板 · Unity X/Z 坐标系</small>
      </div>
      <div class="trajectory-toolbar-actions">
        <em>{{ missionStatus }}</em>
        <button type="button" @click="togglePlayback">{{ playing ? '暂停仿真' : '继续仿真' }}</button>
        <button type="button" @click="resetSimulation">重置轨迹</button>
      </div>
    </header>

    <div class="unity-trajectory-inset">
      <div class="unity-inset-title">TRAJECTORY STATISTICS - ALL AGENTS</div>
      <svg viewBox="0 0 900 500" role="img" aria-label="Unity 风格三机三艇轨迹统计图">
        <defs>
          <clipPath id="unity-trajectory-plot-clip">
            <rect :x="plotRect.x" :y="plotRect.y" :width="plotRect.width" :height="plotRect.height" />
          </clipPath>
        </defs>

        <rect width="900" height="500" class="unity-inset-bg" />
        <rect :x="plotRect.x" :y="plotRect.y" :width="plotRect.width" :height="plotRect.height" class="unity-plot-bg" />
        <rect :x="statisticsRect.x" :y="statisticsRect.y" :width="statisticsRect.width" :height="statisticsRect.height" class="unity-statistics-bg" />

        <g class="unity-grid">
          <template v-for="division in gridDivisions" :key="division">
            <line
              :x1="plotRect.x + (plotRect.width * division) / 5"
              :y1="plotRect.y"
              :x2="plotRect.x + (plotRect.width * division) / 5"
              :y2="plotRect.y + plotRect.height"
            />
            <line
              :x1="plotRect.x"
              :y1="plotRect.y + (plotRect.height * division) / 5"
              :x2="plotRect.x + plotRect.width"
              :y2="plotRect.y + (plotRect.height * division) / 5"
            />
          </template>
        </g>

        <g clip-path="url(#unity-trajectory-plot-clip)">
          <path
            v-for="(item, index) in usvFormationOverlay.items"
            v-show="item.readiness > 0.01"
            :key="`usv-arc-${index}`"
            :d="item.path"
            class="unity-usv-formation"
          />

          <line
            v-for="(edge, index) in uavFormationOverlay.edges"
            v-show="edge.progress > 0.01"
            :key="`uav-edge-${index}`"
            :x1="edge.from.x"
            :y1="edge.from.y"
            :x2="edge.to.x"
            :y2="edge.to.y"
            class="unity-uav-formation"
          />

          <path
            v-for="track in viewTracks"
            :key="`${track.id}-path`"
            :d="track.path"
            fill="none"
            :stroke="track.color"
            class="unity-track-line"
          />

          <g v-for="track in viewTracks" :key="track.id" class="unity-track-marker">
            <rect :x="track.view.x - 3.5" :y="track.view.y - 3.5" width="7" height="7" :fill="track.color" />
            <line :x1="track.view.x" :y1="track.view.y" :x2="track.heading.tip.x" :y2="track.heading.tip.y" :stroke="track.color" />
            <line :x1="track.heading.tip.x" :y1="track.heading.tip.y" :x2="track.heading.wingA.x" :y2="track.heading.wingA.y" :stroke="track.color" />
            <line :x1="track.heading.tip.x" :y1="track.heading.tip.y" :x2="track.heading.wingB.x" :y2="track.heading.wingB.y" :stroke="track.color" />
            <text :x="track.view.x + 3" :y="track.view.y - 5" :fill="track.color" class="unity-short-label">{{ track.shortLabel }}</text>
          </g>

          <text
            v-if="usvFormationOverlay.progress > 0.01"
            :x="usvFormationOverlay.labelPoint.x + 4"
            :y="usvFormationOverlay.labelPoint.y"
            class="unity-formation-label unity-usv-label"
          >USV CIRCLE {{ Math.round(usvFormationOverlay.progress * 100) }}%</text>
          <text
            v-if="uavFormationOverlay.progress > 0.01"
            :x="uavFormationOverlay.labelPoint.x - 126"
            :y="uavFormationOverlay.labelPoint.y"
            class="unity-formation-label unity-uav-label"
          >UAV TRIANGLE {{ Math.round(uavFormationOverlay.progress * 100) }}%</text>
        </g>

        <g class="unity-statistics-text">
          <text :x="statisticsRect.x + 7" :y="statisticsRect.y + 17">TIME&nbsp;&nbsp;{{ elapsedLabel }}</text>
          <g
            v-for="(track, index) in viewTracks"
            :key="`${track.id}-legend`"
            :transform="`translate(0 ${statisticsRect.y + 29 + index * 18})`"
          >
            <rect :x="statisticsRect.x + 7" y="5" width="12" height="3" :fill="track.color" />
            <text :x="statisticsRect.x + 22" y="10">{{ track.label }}&nbsp;&nbsp;{{ formatDistance(track.distance) }}</text>
          </g>
        </g>
      </svg>
    </div>

    <footer class="trajectory-footer">
      <span><i></i>{{ phase }}</span>
      <small>
        USV CIRCLE {{ Math.round(usvFormationOverlay.progress * 100) }}%
        · UAV TRIANGLE {{ Math.round(uavFormationOverlay.progress * 100) }}%
        · Vue 本地仿真
      </small>
    </footer>
  </section>
</template>

<style scoped>
.trajectory-simulator {
  margin-top: 16px;
  overflow: hidden;
  color: #e9fffb;
  background: #07171b;
  border: 1px solid rgba(108, 228, 213, 0.24);
  border-radius: 9px;
}

.trajectory-toolbar,
.trajectory-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 15px;
  background: rgba(10, 38, 43, 0.94);
}

.trajectory-toolbar > div:first-child span,
.trajectory-toolbar > div:first-child strong,
.trajectory-toolbar > div:first-child small {
  display: block;
}

.trajectory-toolbar span {
  color: #72e6d7;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.14em;
}

.trajectory-toolbar strong {
  margin-top: 3px;
  font-size: 15px;
}

.trajectory-toolbar small,
.trajectory-footer small {
  margin-top: 3px;
  color: #87aaa8;
  font-size: 11px;
}

.trajectory-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trajectory-toolbar-actions em,
.trajectory-toolbar-actions button {
  min-height: 31px;
  padding: 0 11px;
  color: #dff8f4;
  font: inherit;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
  background: rgba(114, 230, 215, 0.08);
  border: 1px solid rgba(114, 230, 215, 0.24);
  border-radius: 4px;
}

.trajectory-toolbar-actions button {
  cursor: pointer;
}

.trajectory-toolbar-actions button:hover {
  color: #061113;
  background: #72e6d7;
}

.unity-trajectory-inset {
  padding: 10px;
  background: #03080d;
}

.unity-inset-title {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  color: #e6f5ff;
  font: 12px Arial, sans-serif;
  background: linear-gradient(#27313a, #171d23);
  border: 1px solid #3e4851;
  border-radius: 3px 3px 0 0;
  text-shadow: 0 1px 1px #000;
}

.unity-trajectory-inset svg {
  display: block;
  width: 100%;
  height: auto;
  background: #03080d;
  border: 1px solid #35414a;
  border-top: 0;
  font-family: Arial, sans-serif;
}

.unity-inset-bg {
  fill: #071018;
}

.unity-plot-bg {
  fill: #040c13;
  fill-opacity: 0.96;
}

.unity-statistics-bg {
  fill: #03080d;
  fill-opacity: 0.9;
}

.unity-grid line {
  stroke: #4094b8;
  stroke-opacity: 0.18;
  stroke-width: 1;
}

.unity-track-line {
  stroke-width: 2;
  stroke-linecap: butt;
  stroke-linejoin: miter;
}

.unity-track-marker line {
  stroke-width: 2;
}

.unity-short-label,
.unity-formation-label,
.unity-statistics-text {
  font-size: 11px;
}

.unity-short-label,
.unity-formation-label {
  paint-order: stroke;
  stroke: #040c13;
  stroke-width: 2px;
  font-weight: 400;
}

.unity-usv-formation {
  fill: none;
  stroke: #ff2e24;
  stroke-opacity: 0.82;
  stroke-width: 1.7;
}

.unity-uav-formation {
  stroke: #ffc71f;
  stroke-opacity: 0.88;
  stroke-width: 1.8;
}

.unity-usv-label {
  fill: #ff2e24;
}

.unity-uav-label {
  fill: #ffc71f;
}

.unity-statistics-text {
  fill: #dbefff;
}

.trajectory-footer {
  min-height: 42px;
  border-top: 1px solid rgba(114, 230, 215, 0.16);
}

.trajectory-footer span {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  color: #72e6d7;
  font-size: 11px;
  font-weight: 800;
}

.trajectory-footer span i {
  width: 8px;
  height: 8px;
  background: #72e6d7;
  border-radius: 50%;
  box-shadow: 0 0 12px #72e6d7;
}

@media (max-width: 760px) {
  .trajectory-toolbar,
  .trajectory-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .trajectory-toolbar-actions {
    flex-wrap: wrap;
  }

  .unity-trajectory-inset {
    overflow-x: auto;
  }

  .unity-trajectory-inset svg,
  .unity-inset-title {
    min-width: 700px;
  }
}
</style>
