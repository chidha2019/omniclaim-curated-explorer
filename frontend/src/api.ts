import { SpanStatusCode } from "@opentelemetry/api";
import { token } from "./auth";
import { requestSpan } from "./telemetry";
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId?: string,
    public status?: number,
  ) {
    super(message);
  }
}
export async function get<T>(
  path: string,
  params: URLSearchParams = new URLSearchParams(),
  signal?: AbortSignal,
): Promise<T> {
  const access = await token();
  if (!access)
    throw new ApiError(
      "authentication_required",
      "Your session has ended. Sign in again.",
      undefined,
      401,
    );
  const headers: Record<string, string> = { Authorization: `Bearer ${access}` };
  const span = path === "/api/v1/me" ? undefined : requestSpan(path, headers);
  try {
    const response = await fetch(
      path + (params.size ? "?" + params.toString() : ""),
      {
        headers,
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(45000)])
          : AbortSignal.timeout(45000),
      },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(
        body.code ?? "request_failed",
        body.message ?? "The request could not be completed.",
        response.headers.get("x-request-id") ?? undefined,
        response.status,
      );
    }
    span?.setStatus({ code: SpanStatusCode.OK });
    return (await response.json()) as T;
  } catch (e) {
    span?.setStatus({ code: SpanStatusCode.ERROR });
    throw e;
  } finally {
    span?.end();
  }
}
