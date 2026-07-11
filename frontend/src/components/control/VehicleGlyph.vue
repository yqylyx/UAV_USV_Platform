<script setup lang="ts">
withDefaults(
  defineProps<{
    type: 'UAV' | 'USV'
    size?: 'small' | 'medium' | 'large'
    active?: boolean
  }>(),
  { size: 'medium', active: false },
)
</script>

<template>
  <span class="vehicle-glyph" :class="[type.toLowerCase(), size, { active }]" aria-hidden="true">
    <i class="scan-ring"></i>
    <svg v-if="type === 'UAV'" class="vehicle-model drone-model" viewBox="0 0 100 100">
      <g class="vehicle-stroke" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="22" cy="22" r="13" /><circle cx="78" cy="22" r="13" />
        <circle cx="22" cy="78" r="13" /><circle cx="78" cy="78" r="13" />
        <path d="M31 31 42 42M69 31 58 42M31 69 42 58M69 69 58 58" stroke-width="7" />
      </g>
      <path class="vehicle-fill" d="M50 32c9 0 17 8 17 18S59 68 50 68 33 60 33 50s8-18 17-18Z" />
      <path class="vehicle-cut" d="M43 44h14v12H43z" />
      <circle class="vehicle-fill" cx="50" cy="72" r="5" />
    </svg>
    <svg v-else class="vehicle-model ship-model" viewBox="0 0 100 100">
      <path class="vehicle-stroke" fill="none" stroke="currentColor" stroke-linejoin="round" d="M19 50h62L72 73H30L19 50Z" stroke-width="6" />
      <path class="vehicle-fill" d="M35 35h31l8 15H28l7-15Z" />
      <path class="vehicle-stroke" fill="none" stroke="currentColor" stroke-linecap="round" d="M50 35V17m0 0 13 9M50 17H39" stroke-width="5" />
      <path class="vehicle-cut" d="M40 40h8v7h-8zm13 0h8v7h-8z" />
      <path class="vehicle-stroke waterline" fill="none" stroke="currentColor" stroke-linecap="round" d="M15 82c8-8 15 8 23 0s15 8 23 0 15 8 24 0" stroke-width="5" />
    </svg>
    <i class="axis axis-x"></i>
    <i class="axis axis-y"></i>
  </span>
</template>

<style scoped>
.vehicle-glyph {
  --vehicle-color: #ffc93c;
  --vehicle-rgb: 255, 201, 60;
  position: relative;
  display: inline-grid;
  flex: 0 0 auto;
  place-items: center;
  width: 62px;
  height: 62px;
  color: var(--vehicle-color);
  background:
    radial-gradient(circle, rgba(var(--vehicle-rgb), 0.16), transparent 64%),
    linear-gradient(135deg, rgba(var(--vehicle-rgb), 0.08), transparent 58%);
  border: 1px solid rgba(var(--vehicle-rgb), 0.34);
  border-radius: 8px;
  box-shadow: inset 0 0 20px rgba(var(--vehicle-rgb), 0.06), 0 0 18px rgba(var(--vehicle-rgb), 0.08);
  overflow: hidden;
}

.vehicle-glyph.usv {
  --vehicle-color: #ff6b63;
  --vehicle-rgb: 255, 107, 99;
}

.vehicle-glyph.small { width: 38px; height: 38px; border-radius: 6px; }
.vehicle-glyph.large { width: 78px; height: 78px; }

.vehicle-model {
  position: relative;
  z-index: 2;
  width: 64%;
  height: 64%;
  filter: drop-shadow(0 0 7px rgba(var(--vehicle-rgb), 0.72));
}

.drone-model { width: 68%; height: 68%; }
.ship-model { width: 72%; height: 72%; transform: translateY(-1px); }
.vehicle-stroke { stroke-width: 5; }
.vehicle-fill { fill: currentColor; }
.vehicle-cut { fill: #07171c; }
.waterline { opacity: 0.82; }

.scan-ring {
  position: absolute;
  width: 68%;
  height: 68%;
  border: 1px dashed rgba(var(--vehicle-rgb), 0.32);
  border-radius: 50%;
}

.active .scan-ring { animation: vehicle-scan 7s linear infinite; }
.axis { position: absolute; background: rgba(var(--vehicle-rgb), 0.13); }
.axis-x { width: 100%; height: 1px; }
.axis-y { width: 1px; height: 100%; }

@keyframes vehicle-scan { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
  .active .scan-ring { animation: none; }
}
</style>
