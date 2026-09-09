export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}
function errorText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(errorText).join(" · ");
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (d.message) return String(d.message);
    if (d.msg) return String(d.msg);
    if (d.findings) return errorText(d.findings);
    if (d.detail) return errorText(d.detail);
    return JSON.stringify(detail);
  }
  return "The request could not be completed. Please try again.";
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch {
    throw new Error(
      "The local service is unavailable. Check that Report Foundry is running, then try again.",
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      errorText(data?.error ?? data?.detail ?? data),
      response.status,
      data,
    );
  return data as T;
}
export const post = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const identifier = () => crypto.randomUUID();
export const messageOf = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
