export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = options.signal ? undefined : setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      signal: options.signal ?? controller.signal,
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, body?.detail?.message ?? "The API is unavailable. Try again.");
    }
    return response.status === 204 ? undefined as T : await response.json();
  } finally {
    clearTimeout(timeout);
  }
}
