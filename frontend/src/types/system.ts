export interface SystemHealth {
  status: string
  application: string
  database: string
  databaseVersion: string
  timestamp: string
}

export interface PlatformComponent {
  id: number
  code: string
  name: string
  status: 'READY' | 'PENDING' | string
}

