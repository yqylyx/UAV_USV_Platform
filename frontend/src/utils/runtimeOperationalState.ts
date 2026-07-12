export function normalizeOperationalState(state?: string | null, vehicleType?: 'UAV' | 'USV') {
  const normalized = (state ?? '').trim().toUpperCase()
  if (!normalized) return vehicleType === 'UAV' ? 'GROUNDED' : vehicleType === 'USV' ? 'MOORED' : ''
  if (normalized === 'TAKING_OFF') return 'AIRBORNE'
  if (normalized === 'DEPARTING') return 'SAILING'
  return normalized
}
