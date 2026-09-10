import { apiGet, apiPost } from './api'

const TOKEN_KEY = 'docintel_token'

export interface Token {
  access_token: string
  token_type: string
}

export interface UserOut {
  id: string
  email: string
  created_at: string
}

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function login(email: string, password: string): Promise<Token> {
  return apiPost<Token>('/auth/login', { email, password })
}

export function googleSignIn(idToken: string): Promise<Token> {
  return apiPost<Token>('/auth/google', { id_token: idToken })
}

export function fetchCurrentUser(token: string): Promise<UserOut> {
  return apiGet<UserOut>('/auth/me', token)
}
