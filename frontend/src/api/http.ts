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
  // Protected write APIs attach the token returned by /auth/csrf explicitly.
  // Do not let Axios replace that encoded token with the raw cookie value.
  withXSRFToken: false,
  xsrfCookieName: 'XSRF-TOKEN',
  xsrfHeaderName: 'X-XSRF-TOKEN',
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const message =
      error.response?.data?.message ??
      (error.response ? `后端请求失败（HTTP ${error.response.status}）` : '无法连接后端服务')
    return Promise.reject(
      new ApiClientError(message, error.response?.status, error.response?.data?.code),
    )
  },
)
