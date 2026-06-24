import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { CsrfToken, CurrentUser, LoginPayload } from '@/types/auth'

export async function fetchCsrfToken(): Promise<CsrfToken> {
  const response = await http.get<ApiResponse<CsrfToken>>('/auth/csrf')
  return response.data.data
}

export async function login(payload: LoginPayload): Promise<CurrentUser> {
  const response = await http.post<ApiResponse<CurrentUser>>('/auth/login', payload)
  return response.data.data
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await http.get<ApiResponse<CurrentUser>>('/auth/me')
  return response.data.data
}

export async function logout(): Promise<void> {
  const csrfToken = await fetchCsrfToken()
  await http.post<ApiResponse<null>>('/auth/logout', undefined, {
    headers: {
      [csrfToken.headerName]: csrfToken.token,
    },
  })
}
