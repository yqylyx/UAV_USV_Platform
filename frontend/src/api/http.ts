import axios from 'axios'
import type { AxiosError } from 'axios'

import type { ApiErrorResponse } from '@/types/api'
import { useConnectivityStore } from '@/stores/connectivity'

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
  // The backend uses a remote MySQL instance. Five seconds was shorter than
  // an occasional connection/lock recovery and turned a slow response into a
  // misleading "cannot connect" error on otherwise healthy deployments.
  timeout: 12000,
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
  (response) => {
    useConnectivityStore().markOnline()
    return response
  },
  async (error: AxiosError<ApiErrorResponse>) => {
    const connectivity = useConnectivityStore()
    const config = error.config as (typeof error.config & { __safeRetryCount?: number })
    const safeMethod = (config?.method ?? 'get').toLowerCase() === 'get'
    const transient = !error.response || error.response.status >= 500
    const retries = config?.__safeRetryCount ?? 0
    if (safeMethod && transient && retries < 2 && config) {
      config.__safeRetryCount = retries + 1
      await new Promise(resolve => window.setTimeout(resolve, retries === 0 ? 300 : 900))
      return http.request(config)
    }
    let message: string
    if (error.response) {
      message = error.response.data?.message ?? `后端请求失败（HTTP ${error.response.status}）`
      if (error.response.status === 401) connectivity.markFailure('AUTH_EXPIRED', '登录状态已失效，请重新登录')
      else if (error.response.status >= 500) connectivity.markFailure('DEGRADED', message)
    } else if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      message = '后端响应超时，请稍后重试；若持续出现请检查数据库连接'
      connectivity.markFailure('TIMEOUT', message)
    } else if (typeof navigator !== 'undefined' && !navigator.onLine) {
      message = '当前网络已断开，请检查本机网络连接'
      connectivity.markFailure('OFFLINE', message)
    } else {
      message = '后端服务暂不可达，系统正在等待连接恢复'
      connectivity.markFailure('OFFLINE', message)
    }
    return Promise.reject(
      new ApiClientError(message, error.response?.status, error.response?.data?.code ?? error.code),
    )
  },
)
