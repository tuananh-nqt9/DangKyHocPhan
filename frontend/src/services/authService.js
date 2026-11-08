// Authentication Service
import apiClient from './apiClient';

/**
 * Login with student_id and password.
 * POST /api/v1/auth/login
 * Returns: { access_token, token_type, expires_in, refresh_token, refresh_expires_in, student }
 */
export async function login(studentId, password) {
  const response = await apiClient.post('/v1/auth/login', {
    student_id: studentId,
    password: password,
  });
  return response.data; // { success, code, message, data: AuthTokenData }
}

/**
 * Refresh tokens.
 * POST /api/v1/auth/refresh
 */
export async function refreshTokens(refreshToken) {
  const response = await apiClient.post('/v1/auth/refresh', {
    refresh_token: refreshToken,
  });
  return response.data;
}

/**
 * Logout — revoke current session.
 * POST /api/v1/auth/logout
 */
export async function logout(refreshToken) {
  const response = await apiClient.post('/v1/auth/logout', {
    refresh_token: refreshToken,
  });
  return response.data;
}

/**
 * Save auth data to localStorage after login/SSO.
 */
export function saveAuthData(data) {
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  localStorage.setItem('user', JSON.stringify(data.student));
}

/**
 * Clear all auth data.
 */
export function clearAuthData() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  sessionStorage.removeItem('queue_token');
}

/**
 * Get current user from localStorage.
 */
export function getCurrentUser() {
  const userStr = localStorage.getItem('user');
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
}

/**
 * Check if user is authenticated.
 */
export function isAuthenticated() {
  return !!localStorage.getItem('access_token');
}

/**
 * Get user's role.
 */
export function getUserRole() {
  const user = getCurrentUser();
  return user?.role || null;
}
