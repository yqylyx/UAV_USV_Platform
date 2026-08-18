<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { RadarItem } from '@/types/sensor'

const props = defineProps<{
  items: RadarItem[]
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
let resizeObserver: ResizeObserver | undefined

function draw() {
  const element = canvas.value
  if (!element) return

  const width = element.clientWidth
  const height = element.clientHeight
  if (width <= 0 || height <= 0) return

  const pixelRatio = window.devicePixelRatio || 1
  element.width = Math.round(width * pixelRatio)
  element.height = Math.round(height * pixelRatio)

  const context = element.getContext('2d')
  if (!context) return
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  context.clearRect(0, 0, width, height)

  const centerX = width / 2
  const centerY = height / 2
  const radius = Math.min(width, height) * 0.44

  context.strokeStyle = 'rgba(117, 203, 205, .22)'
  context.lineWidth = 0.5
  for (const ratio of [1, 29 / 44, 14 / 44]) {
    context.beginPath()
    context.arc(centerX, centerY, radius * ratio, 0, Math.PI * 2)
    context.stroke()
  }
  context.beginPath()
  context.moveTo(centerX, centerY - radius)
  context.lineTo(centerX, centerY + radius)
  context.moveTo(centerX - radius, centerY)
  context.lineTo(centerX + radius, centerY)
  context.stroke()

  const points = props.items.filter(
    (item) => item.kind === 'POINTCLOUD' && Number.isFinite(item.x) && Number.isFinite(item.y),
  )
  let maxAbs = 1
  for (const point of points) {
    maxAbs = Math.max(maxAbs, Math.abs(point.x!), Math.abs(point.y!))
  }
  const scale = radius / maxAbs

  context.fillStyle = 'rgba(92, 231, 183, .65)'
  for (const point of points) {
    const x = centerX + point.y! * scale
    const y = centerY - point.x! * scale
    context.fillRect(x - 0.75, y - 0.75, 1.5, 1.5)
  }

  context.fillStyle = '#65ddcf'
  context.beginPath()
  context.arc(centerX, centerY, 3, 0, Math.PI * 2)
  context.fill()
}

watch(() => props.items, () => nextTick(draw))

onMounted(() => {
  resizeObserver = new ResizeObserver(draw)
  if (canvas.value) resizeObserver.observe(canvas.value)
  draw()
})

onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<template>
  <canvas ref="canvas" class="pointcloud-canvas" role="img" aria-label="2D pointcloud overview" />
</template>

<style scoped>
.pointcloud-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
