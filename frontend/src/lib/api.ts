export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController();
  const timeout = options.signal ? undefined : setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      signal: options.signal ?? controller.signal,
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const message = body?.detail?.message ?? (typeof body?.detail === "string" ? body.detail : null);
      throw new ApiError(response.status, message ?? (response.status === 413 ? "The file exceeds the upload limit." : "The API is unavailable. Try again."), body?.detail);
    }
    return response.status === 204 ? undefined as T : await response.json();
  } finally {
    clearTimeout(timeout);
  }
}
