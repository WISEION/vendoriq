/**
 * The only way the web app reaches data.
 *
 * Every response is either the payload or the error envelope
 * `{ error: { code, message, details } }` — see docs/openapi.yaml. No business rule is
 * evaluated here: the client transports, the server decides.
 */
export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.error.code;
    this.details = body.error.details;
  }
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

function csrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)vendoriq_csrf=([^;]+)/);
  return match?.[1] ?? null;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  // FormData sets its own multipart boundary; only stamp JSON on a body that needs it.
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = csrfToken();
  if (token && init.method && init.method !== 'GET') {
    headers.set('X-CSRF-Token', token);
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });

  if (response.status === 204) return undefined as T;

  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiError(response.status, payload as ApiErrorBody);
  }
  return payload as T;
}

/** For the handful of endpoints that return a file (`.xlsx` / `.pdf` exports) instead of JSON. */
export async function apiFetchBinary(path: string, method: string): Promise<Blob> {
  const headers = new Headers();
  const token = csrfToken();
  if (token && method !== 'GET') {
    headers.set('X-CSRF-Token', token);
  }

  const response = await fetch(`${BASE_URL}${path}`, { method, headers, credentials: 'include' });

  if (!response.ok) {
    const payload = (await response.json()) as ApiErrorBody;
    throw new ApiError(response.status, payload);
  }
  return response.blob();
}

export interface Health {
  status: 'ok';
  version: string;
  app_env: 'development' | 'staging' | 'production';
  auth_mode: 'test' | 'live';
  storage_backend: 'local' | 's3';
}

export const getHealth = () => apiFetch<Health>('/health');
