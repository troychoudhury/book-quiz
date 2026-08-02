import axios from 'axios';

import { useAuthStore } from '../stores/authStore';
import type {
  BookDetail,
  BookSearchResponse,
  CompleteQuizResponse,
  LoginRequest,
  RegisterRequest,
  StartQuizResponse,
  AnswerResponse,
  TokenResponse,
  UserResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// ── Auth interceptor: attach access token from the auth store ─────────
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Token refresh on 401 (single-flight) ──────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (v: unknown) => void;
  reject: (e: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error);
    else prom.resolve(token);
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post<TokenResponse>(`${API_BASE}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
        processQueue(null, data.access_token);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        useAuthStore.getState().logout();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  },
);

// ── Auth API ────────────────────────────────────────────────────────────
export const authApi = {
  register: (data: RegisterRequest) => api.post<UserResponse>('/api/v1/auth/register', data),
  login: (data: LoginRequest) => api.post<TokenResponse>('/api/v1/auth/login', data),
  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/api/v1/auth/refresh', { refresh_token }),
};

// ── Books API ───────────────────────────────────────────────────────────
export const booksApi = {
  search: (q: string, page = 1, size = 20) =>
    api.get<BookSearchResponse>('/api/v1/books', { params: { q, page, size } }),
  getById: (id: string) => api.get<BookDetail>(`/api/v1/books/${id}`),
};

// ── Quiz API ────────────────────────────────────────────────────────────
export const quizApi = {
  start: (book_id: string) => api.post<StartQuizResponse>('/api/v1/quizzes/start', { book_id }),
  answer: (attemptId: string, question_id: string, choice_id: string) =>
    api.post<AnswerResponse>(`/api/v1/quizzes/${attemptId}/answer`, { question_id, choice_id }),
  complete: (attemptId: string, email?: string) =>
    api.post<CompleteQuizResponse>(`/api/v1/quizzes/${attemptId}/complete`, { email }),
};

export default api;
