export interface AdaptiveScenarioPlan {
  uavCount: number
  usvCount: number
  effectiveScale: number
  protectedCount: number
  threatCount: number
  simultaneousThreats: number
  worldWidth: number
  worldHeight: number
  targetCount: number
  realtimeTier: 'PHASE_TWO_REALTIME' | 'CAPACITY_ONLY'
}

export function deriveAdaptiveScenarioPlan(uavInput: number, usvInput: number): AdaptiveScenarioPlan {
  const uavCount = Math.max(1, Math.min(128, Math.trunc(uavInput)))
  const usvCount = Math.max(1, Math.min(128, Math.trunc(usvInput)))
  const effectiveScale = Math.min(uavCount, usvCount)
  let protectedCount = 1
  let threatCount = 1
  let simultaneousThreats = 1
  // Keep enough open water for the 120 m initial threat offset and the
  // mandatory 80 m visible escape run used by small escort experiments.
  let worldWidth = 360
  let worldHeight = 280
  if (effectiveScale >= 25) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 4, 4, 600, 460]
  else if (effectiveScale >= 20) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 3, 3, 520, 400]
  else if (effectiveScale >= 15) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 3, 3, 420, 320]
  else if (effectiveScale >= 10) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 2, 2, 360, 280]
  if (effectiveScale > 30) {
    // Escort always protects one authoritative vessel. Fleet growth adds
    // concurrent threats and response capacity, never duplicate objectives.
    protectedCount = 1
    threatCount = Math.min(8, 4 + Math.floor((effectiveScale - 31) / 16))
    simultaneousThreats = Math.min(4, Math.max(2, Math.ceil(threatCount / 2)))
    worldWidth = 600 + Math.min(600, (effectiveScale - 30) * 8)
    worldHeight = 460 + Math.min(440, (effectiveScale - 30) * 6)
  }
  return {
    uavCount, usvCount, effectiveScale, protectedCount, threatCount,
    simultaneousThreats, worldWidth, worldHeight,
    targetCount: protectedCount + threatCount,
    realtimeTier: effectiveScale <= 30 ? 'PHASE_TWO_REALTIME' : 'CAPACITY_ONLY',
  }
}
