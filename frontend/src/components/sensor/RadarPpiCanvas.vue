<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { RadarItem } from '@/types/sensor'

const props = defineProps<{ items: RadarItem[]; selectedId?: string }>()
const emit = defineEmits<{ select: [item: RadarItem] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
let animationFrame = 0
let sweepAngle = 0
let lastTime = 0
let projected: Array<{ item: RadarItem; x: number; y: number }> = []

function displayBearing(bearing: number) {
  return (360 - bearing) % 360
}

function polar(item: RadarItem) {
  if (item.range != null && item.bearing != null) {
    const angle = displayBearing(item.bearing) * Math.PI / 180
    return { x: Math.sin(angle) * item.range, y: Math.cos(angle) * item.range }
  }
  if (item.x != null && item.y != null) return { x: -item.y, y: item.x }
  return null
}

function draw(now = performance.now()) {
  const element = canvas.value
  if (!element) return
  const width = element.clientWidth
  const height = element.clientHeight
  if (!width || !height) return
  const ratio = window.devicePixelRatio || 1
  if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
    element.width = Math.round(width * ratio)
    element.height = Math.round(height * ratio)
  }
  const context = element.getContext('2d')
  if (!context) return
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.clearRect(0, 0, width, height)
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * .45
  const points = props.items.map(item => ({ item, value: polar(item) })).filter(entry => entry.value)
  const maxRange = Math.max(100, ...points.map(entry => Math.hypot(entry.value!.x, entry.value!.y)))

  context.strokeStyle = 'rgba(74,218,203,.19)'
  context.lineWidth = 1
  for (let ring = 1; ring <= 5; ring += 1) {
    context.beginPath(); context.arc(cx, cy, radius * ring / 5, 0, Math.PI * 2); context.stroke()
    context.fillStyle = 'rgba(148,201,199,.68)'; context.font = '10px sans-serif'; context.textAlign = 'left'
    context.fillText(`${Math.round(maxRange * ring / 5)} m`, cx + 5, cy - radius * ring / 5 + 12)
  }
  for (let degree = 0; degree < 360; degree += 30) {
    const angle = degree * Math.PI / 180
    context.beginPath(); context.moveTo(cx, cy)
    context.lineTo(cx + Math.sin(angle) * radius, cy - Math.cos(angle) * radius); context.stroke()
    context.fillStyle = '#72999b'; context.font = '11px sans-serif'; context.textAlign = 'center'
    context.fillText(`${degree}°`, cx + Math.sin(angle) * (radius + 17), cy - Math.cos(angle) * (radius + 17) + 4)
  }

  const elapsed = Math.min(32, Math.max(0, now - lastTime)); lastTime = now
  sweepAngle = (sweepAngle + elapsed * .045) % 360
  const sweep = sweepAngle * Math.PI / 180
  const gradient = context.createRadialGradient(cx, cy, 0, cx, cy, radius)
  gradient.addColorStop(0, 'rgba(57,231,190,.24)'); gradient.addColorStop(1, 'rgba(57,231,190,0)')
  context.fillStyle = gradient
  context.beginPath(); context.moveTo(cx, cy); context.arc(cx, cy, radius, sweep - .34, sweep); context.closePath(); context.fill()
  context.strokeStyle = 'rgba(77,242,202,.9)'; context.beginPath(); context.moveTo(cx, cy)
  context.lineTo(cx + Math.cos(sweep) * radius, cy + Math.sin(sweep) * radius); context.stroke()

  projected = []
  for (const entry of points) {
    const x = cx + entry.value!.x / maxRange * radius
    const y = cy - entry.value!.y / maxRange * radius
    projected.push({ item: entry.item, x, y })
    const selected = entry.item.id === props.selectedId
    context.fillStyle = entry.item.kind === 'OBSTACLE'
      ? '#ffad45'
      : entry.item.kind === 'RADAR_RETURN'
        ? '#55d8ff'
        : '#62e7bc'
    context.shadowColor = context.fillStyle; context.shadowBlur = selected ? 15 : 7
    context.beginPath(); context.arc(x, y, selected ? 6 : 3, 0, Math.PI * 2); context.fill()
    context.shadowBlur = 0
    if (selected) {
      context.strokeStyle = '#ffca58'; context.lineWidth = 2
      context.strokeRect(x - 11, y - 11, 22, 22)
      const anchorX = x < cx ? 34 : width - 34
      const elbowX = x < cx ? x - 34 : x + 34
      const anchorY = Math.max(32, Math.min(height - 32, y - 52))
      context.beginPath(); context.moveTo(x, y); context.lineTo(elbowX, anchorY); context.lineTo(anchorX, anchorY); context.stroke()
      context.fillStyle = '#ffca58'; context.font = '700 11px sans-serif'; context.textAlign = x < cx ? 'left' : 'right'
      context.fillText(entry.item.id, anchorX, anchorY - 6)
    }
  }
  context.fillStyle = '#65ddcf'; context.beginPath(); context.arc(cx, cy, 4, 0, Math.PI * 2); context.fill()
  animationFrame = window.requestAnimationFrame(draw)
}

function selectPoint(event: MouseEvent) {
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return
  const x = event.clientX - rect.left, y = event.clientY - rect.top
  const nearest = projected.map(point => ({ point, distance: Math.hypot(point.x - x, point.y - y) }))
    .filter(entry => entry.distance <= 18).sort((a, b) => a.distance - b.distance)[0]
  if (nearest) emit('select', nearest.point.item)
}

onMounted(() => {
  animationFrame = window.requestAnimationFrame(draw)
})
onBeforeUnmount(() => { window.cancelAnimationFrame(animationFrame) })
</script>

<template><canvas ref="canvas" class="radar-ppi" aria-label="雷达PPI扫描" @click="selectPoint" /></template>

<style scoped>
.radar-ppi{display:block;width:100%;height:100%;cursor:crosshair}
</style>
