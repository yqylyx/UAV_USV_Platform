export interface CurrentUser {
  username: string
  role: 'ADMIN' | 'OPERATOR' | 'VIEWER' | string
}

export interface LoginPayload {
  username: string
  password: string
}

export interface CsrfToken {
  headerName: string
  parameterName: string
  token: string
}
