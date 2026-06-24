import axios from 'axios'
import type { AxiosError } from 'axios'

import type { ApiErrorResponse } from '@/types/api'

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 5000,
  withCredentials: true,
  xsrfCookieName: 'XSRF-TOKEN',
  xsrfHeaderName: 'X-XSRF-TOKEN',
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const message = error.response?.data?.message ?? '无法连接后端服务'
    return Promise.reject(
      new ApiClientError(message, error.response?.status, error.response?.data?.code),
    )
  },
)
