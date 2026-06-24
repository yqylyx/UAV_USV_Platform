export interface ApiResponse<T> {
  code: string
  message: string
  data: T
  timestamp: string
}

export interface ApiErrorResponse {
  code: string
  message: string
  data: null
  timestamp: string
}

export interface PageResponse<T> {
  records: T[]
  total: number
  page: number
  size: number
  totalPages: number
}
