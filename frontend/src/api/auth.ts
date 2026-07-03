import { http } from './http'
import type { ApiResponse } from '@/types/api'
import type { CsrfToken, CurrentUser, LoginPayload } from '@/types/auth'

function readCookie(name: string): string {
  if (typeof document === 'undefined') return ''
  const cookieText = document.cookie || ''
  const cookie = cookieText.split('; ').find((item) => item.startsWith(`${name}=`))
  return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : ''
}

export async function fetchCsrfToken(): Promise<CsrfToken> {
  const response = await http.get<ApiResponse<CsrfToken>>('/auth/csrf')
  const token = readCookie('XSRF-TOKEN') || response.data.data.token
  return { ...response.data.data, token }
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
