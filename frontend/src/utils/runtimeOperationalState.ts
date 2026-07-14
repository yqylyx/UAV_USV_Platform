export function normalizeOperationalState(state?: string | null, vehicleType?: 'UAV' | 'USV') {
  const normalized = (state ?? '').trim().toUpperCase()
  if (!normalized) return vehicleType === 'UAV' ? 'GROUNDED' : vehicleType === 'USV' ? 'MOORED' : ''
  if (normalized === 'HOVERING') return 'HOLDING'
  return normalized
}

export function isStableMissionReadyState(state?: string | null, vehicleType?: 'UAV' | 'USV') {
  const normalized = normalizeOperationalState(state, vehicleType)
  return vehicleType === 'UAV'
    ? normalized === 'AIRBORNE' || normalized === 'HOLDING'
    : vehicleType === 'USV'
      ? normalized === 'SAILING' || normalized === 'HOLDING'
      : false
}

export function isTransitionalOperationalState(state?: string | null) {
  return ['TAKING_OFF', 'DEPARTING', 'RETURNING', 'LANDING'].includes(
    normalizeOperationalState(state),
  )
}
