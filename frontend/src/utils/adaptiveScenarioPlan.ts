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
  const uavCount = Math.max(1, Math.min(15, Math.trunc(uavInput)))
  const usvCount = Math.max(1, Math.min(15, Math.trunc(usvInput)))
  const effectiveScale = Math.min(uavCount, usvCount)
  let protectedCount = 1
  let threatCount = 1
  let simultaneousThreats = 1
  // Keep enough open water for the 120 m initial threat offset and the
  // mandatory 80 m visible escape run used by small escort experiments.
  let worldWidth = 360
  let worldHeight = 280
  if (effectiveScale >= 15) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 3, 2, 420, 320]
  else if (effectiveScale >= 10) [protectedCount, threatCount, simultaneousThreats, worldWidth, worldHeight] = [1, 2, 2, 360, 280]
  return {
    uavCount, usvCount, effectiveScale, protectedCount, threatCount,
    simultaneousThreats, worldWidth, worldHeight,
    targetCount: protectedCount + threatCount,
    realtimeTier: 'PHASE_TWO_REALTIME',
  }
}
