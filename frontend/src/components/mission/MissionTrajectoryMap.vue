<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { RuntimeCommandStatus, RuntimeCommandType } from '@/api/runtimeControl'

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

type OperationalState = 'STANDBY' | 'ACTIVE' | 'HOLDING' | 'RETURNING' | 'STOPPED' | 'ERROR'

type DeviceMotionState = {
  time: number
  state: OperationalState
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
    selectedDeviceCode?: string
    commandFeedback?: Record<string, RuntimeCommandStatus | undefined>
  }>(),
  {
    missionName: '三机三艇协同围捕预演',
    missionStatus: 'READY',
    selectedDeviceCode: 'uav-02',
    commandFeedback: () => ({}),
  },
)

const emit = defineEmits<{
  selectDevice: [deviceCode: string]
}>()

// Exact colors used by ChaseCamera.cs.
const unityColors = {
  usv: '#ff2e24',
  uav: '#ffc71f',
  target: '#1f75ff',
}

const definitions: TrackDefinition[] = [
  { id: 'usv-01', label: 'USV-01', shortLabel: 'S1', kind: 'USV', color: unityColors.usv, angle: 0 },
  { id: 'usv-02', label: 'USV-02', shortLabel: 'S2', kind: 'USV', color: unityColors.usv, angle: 120 },
  { id: 'usv-03', label: 'USV-03', shortLabel: 'S3', kind: 'USV', color: unityColors.usv, angle: 240 },
  { id: 'uav-01', label: 'UAV-01', shortLabel: 'A1', kind: 'UAV', color: unityColors.uav, angle: 60 },
  { id: 'uav-02', label: 'UAV-02', shortLabel: 'A2', kind: 'UAV', color: unityColors.uav, angle: 180 },
  { id: 'uav-03', label: 'UAV-03', shortLabel: 'A3', kind: 'UAV', color: unityColors.uav, angle: 300 },
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
const deviceMotion = ref<Record<string, DeviceMotionState>>({})
const localFeedback = ref<Record<string, RuntimeCommandStatus | undefined>>({})
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

function initializeDeviceMotion() {
  const active = props.missionStatus === 'RUNNING'
  deviceMotion.value = Object.fromEntries(
    definitions
      .filter((definition) => definition.kind !== 'TARGET')
      .map((definition) => [definition.id, { time: active ? 18 : 0, state: active ? 'ACTIVE' : 'STANDBY' }]),
  )
}

function feedbackFor(deviceCode: string) {
  return localFeedback.value[deviceCode] ?? props.commandFeedback[deviceCode]
}

function updateTracks(time: number, delta: number, sample: boolean) {
  for (const track of tracks.value) {
    const motion = deviceMotion.value[track.id]
    if (motion && playing.value) {
      if (motion.state === 'ACTIVE') motion.time += delta
      if (motion.state === 'RETURNING') motion.time = Math.max(0, motion.time - delta * 1.7)
      if (motion.state === 'RETURNING' && motion.time <= 0) {
        motion.state = track.kind === 'UAV' ? 'STANDBY' : 'STOPPED'
      }
    }
    const next = positionFor(track, track.kind === 'TARGET' ? time : motion?.time ?? 0)
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
  deviceMotion.value = { ...deviceMotion.value }
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

const formationRings = computed(() => {
  const center = toView(targetTrack.value?.position ?? { x: 0, z: 0 })
  const pixelsPerMeter = plotRect.width / Math.max(1, worldBounds.value.maxX - worldBounds.value.minX)
  return {
    center,
    capture: captureRadius * pixelsPerMeter,
    defense: defenseRadius * pixelsPerMeter,
  }
})

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
  const readiness = drones.map((drone) => {
    const airborne = (deviceMotion.value[drone.id]?.time ?? 0) >= 5
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
  const states = Object.values(deviceMotion.value).map((item) => item.state)
  if (states.some((state) => state === 'ERROR')) return '载具指令异常'
  if (states.some((state) => state === 'RETURNING')) return '编组返航'
  if (states.length && states.every((state) => state === 'HOLDING')) return '编组安全保持'
  const maxMotionTime = Math.max(0, ...Object.values(deviceMotion.value).map((item) => item.time))
  if (maxMotionTime < 8) return 'UAV 起飞 / USV 离泊'
  if (maxMotionTime < 22) return '目标搜索与接触'
  if (maxMotionTime < 52) return '三角编队协同收敛'
  return '合围半径保持'
})

const elapsedLabel = computed(() => {
  const totalSeconds = Math.max(0, Math.floor(elapsed.value))
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
})

const phaseSteps = ['编组待命', 'UAV起飞 / USV离泊', '目标搜索', '协同合围', '半径保持', '全体返航']
const activePhaseIndex = computed(() => {
  if (phase.value.includes('返航')) return 5
  if (phase.value.includes('保持')) return phase.value.includes('半径') ? 4 : 3
  if (phase.value.includes('收敛')) return 3
  if (phase.value.includes('搜索')) return 2
  if (phase.value.includes('起飞')) return 1
  return 0
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
  initializeDeviceMotion()
  tracks.value = buildTracks(0)
  playing.value = true
}

function applyVehicleCommand(
  commandType: RuntimeCommandType,
  deviceCodes: string[],
  statuses: RuntimeCommandStatus[],
) {
  deviceCodes.forEach((deviceCode, index) => {
    const normalizedCode = deviceCode.trim().toLowerCase()
    const status = statuses[index] ?? 'PENDING'
    localFeedback.value = { ...localFeedback.value, [normalizedCode]: status }
    if (status !== 'ACKNOWLEDGED') {
      if (status === 'FAILED' || status === 'TIMEOUT') {
        const motion = deviceMotion.value[normalizedCode]
        if (motion) motion.state = 'ERROR'
      }
      return
    }
    const motion = deviceMotion.value[normalizedCode]
    if (!motion) return
    if (commandType === 'UAV_TAKEOFF' || commandType === 'UAV_RESUME' || commandType === 'USV_DEPART' || commandType === 'USV_RESUME') {
      motion.state = 'ACTIVE'
      playing.value = true
    } else if (commandType === 'UAV_HOVER' || commandType === 'USV_HOLD') {
      motion.state = 'HOLDING'
    } else if (commandType === 'UAV_RETURN' || commandType === 'USV_RETURN') {
      motion.state = 'RETURNING'
      playing.value = true
    } else if (commandType === 'UAV_LAND' || commandType === 'UAV_EMERGENCY_LAND') {
      motion.state = 'RETURNING'
    } else if (commandType === 'USV_STOP' || commandType === 'USV_EMERGENCY_STOP') {
      motion.state = 'STOPPED'
    }
  })
  deviceMotion.value = { ...deviceMotion.value }
}

function applyMissionAction(action: string) {
  if (action === 'pause' || action === 'abort') playing.value = false
  if (action === 'start' || action === 'resume' || action === 'deploy' || action === 'return') playing.value = true
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
    updateTracks(elapsed.value, delta, shouldSample)
  }

  animationFrame = window.requestAnimationFrame(animate)
}

onMounted(() => {
  initializeDeviceMotion()
  tracks.value = buildTracks(0)
  animationFrame = window.requestAnimationFrame(animate)
})

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrame)
})

defineExpose({ applyVehicleCommand, applyMissionAction })
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
          <circle
            :cx="formationRings.center.x"
            :cy="formationRings.center.y"
            :r="formationRings.defense"
            class="unity-defense-ring"
          />
          <circle
            :cx="formationRings.center.x"
            :cy="formationRings.center.y"
            :r="formationRings.capture"
            class="unity-capture-ring"
          />
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

          <g
            v-for="track in viewTracks"
            :key="track.id"
            class="unity-track-marker"
            :class="[
              feedbackFor(track.id)?.toLowerCase(),
              { selected: track.id === selectedDeviceCode.trim().toLowerCase(), selectable: track.kind !== 'TARGET' },
            ]"
            @click="track.kind !== 'TARGET' && emit('selectDevice', track.id)"
          >
            <circle
              v-if="track.kind !== 'TARGET' && (track.id === selectedDeviceCode.trim().toLowerCase() || feedbackFor(track.id))"
              :cx="track.view.x"
              :cy="track.view.y"
              :r="track.id === selectedDeviceCode.trim().toLowerCase() ? 11 : 8"
              class="unity-command-ring"
            />
            <rect :x="track.view.x - 3.5" :y="track.view.y - 3.5" width="7" height="7" :fill="track.color" />
            <line :x1="track.view.x" :y1="track.view.y" :x2="track.heading.tip.x" :y2="track.heading.tip.y" :stroke="track.color" />
            <line :x1="track.heading.tip.x" :y1="track.heading.tip.y" :x2="track.heading.wingA.x" :y2="track.heading.wingA.y" :stroke="track.color" />
            <line :x1="track.heading.tip.x" :y1="track.heading.tip.y" :x2="track.heading.wingB.x" :y2="track.heading.wingB.y" :stroke="track.color" />
            <text :x="track.view.x + 3" :y="track.view.y - 5" :fill="track.color" class="unity-short-label">{{ track.shortLabel }}</text>
            <text
              v-if="track.kind !== 'TARGET' && feedbackFor(track.id)"
              :x="track.view.x + 8"
              :y="track.view.y + 12"
              class="unity-command-label"
            >{{ feedbackFor(track.id) }}</text>
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

    <div class="trajectory-phase-strip" aria-label="任务阶段">
      <div
        v-for="(step, index) in phaseSteps"
        :key="step"
        :class="{ completed: index < activePhaseIndex, active: index === activePhaseIndex }"
      >
        <b>{{ index + 1 }}</b>
        <span>{{ step }}</span>
      </div>
    </div>

    <footer class="trajectory-footer">
      <span><i></i>{{ phase }}</span>
      <small>
        USV CIRCLE {{ Math.round(usvFormationOverlay.progress * 100) }}%
        · UAV TRIANGLE {{ Math.round(uavFormationOverlay.progress * 100) }}%
        · {{ selectedDeviceCode.toUpperCase() }}
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

.trajectory-phase-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 5px;
  padding: 11px 13px;
  background: rgba(5, 22, 28, 0.97);
  border-top: 1px solid rgba(114, 230, 215, 0.13);
}

.trajectory-phase-strip div {
  position: relative;
  display: flex;
  gap: 7px;
  align-items: center;
  min-width: 0;
  color: #607f80;
  font-size: 9px;
}

.trajectory-phase-strip div::after {
  position: absolute;
  right: -4px;
  width: 6px;
  height: 1px;
  content: '';
  background: rgba(114, 230, 215, 0.2);
}

.trajectory-phase-strip div:last-child::after {
  display: none;
}

.trajectory-phase-strip b {
  display: grid;
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  place-items: center;
  border: 1px solid #426466;
  border-radius: 50%;
}

.trajectory-phase-strip .completed,
.trajectory-phase-strip .active {
  color: #bffaf1;
}

.trajectory-phase-strip .completed b {
  color: #051313;
  background: #62d99b;
  border-color: #62d99b;
}

.trajectory-phase-strip .active b {
  color: #061519;
  background: #59daf1;
  border-color: #59daf1;
  box-shadow: 0 0 12px rgba(89, 218, 241, 0.55);
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

.unity-track-marker.selectable {
  cursor: pointer;
}

.unity-command-ring {
  fill: rgba(79, 224, 241, 0.08);
  stroke: #5eeaff;
  stroke-width: 1.7;
}

.unity-track-marker.dispatched .unity-command-ring,
.unity-track-marker.pending .unity-command-ring {
  stroke: #ffd56b;
  stroke-dasharray: 3 2;
  animation: trajectory-command-pulse 1.1s ease-in-out infinite;
}

.unity-track-marker.acknowledged .unity-command-ring {
  stroke: #67eea6;
}

.unity-track-marker.failed .unity-command-ring,
.unity-track-marker.timeout .unity-command-ring {
  stroke: #ff5c55;
}

.unity-command-label {
  fill: #d9fffa;
  font-size: 8px;
  paint-order: stroke;
  stroke: #040c13;
  stroke-width: 2px;
}

@keyframes trajectory-command-pulse {
  50% { opacity: 0.36; }
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

.unity-defense-ring,
.unity-capture-ring {
  fill: none;
  stroke-width: 1.2;
  stroke-dasharray: 5 4;
}

.unity-defense-ring {
  stroke: #47dcec;
  stroke-opacity: 0.52;
}

.unity-capture-ring {
  stroke: #ff5149;
  stroke-opacity: 0.72;
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
