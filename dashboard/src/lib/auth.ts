/**
 * localStorage token helpers for DEEP6 dashboard.
 * Per D-23: Simple bearer token auth stored in localStorage.
 * Per T-10-05: Token readable in devtools — acceptable for single-operator scope.
 */

const TOKEN_KEY = "deep6_ws_token"

export const getToken = (): string | null => {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export const setToken = (t: string): void => {
  localStorage.setItem(TOKEN_KEY, t)
}

export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY)
}
