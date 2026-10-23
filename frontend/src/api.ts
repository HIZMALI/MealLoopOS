export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      signal: options?.signal ?? AbortSignal.timeout(35_000),
    });
  } catch {
    throw new Error(
      "The service is unreachable or took too long to respond. A sleeping demo host may need about a minute to wake. Wait briefly, then retry. For local use, start the backend on port 8080.",
    );
  }
  const json = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = json?.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    const errors = Array.isArray(detail)
      ? detail
          .map(
            (e: { loc: string[]; msg: string }) =>
              `${e.loc.join(".")}: ${e.msg}`,
          )
          .join("; ")
      : detail?.errors
          ?.map(
            (e: { source_row: number; field: string; message: string }) =>
              `Row ${e.source_row}, ${e.field}: ${e.message}`,
          )
          .join("\n");
    const fallback =
      response.status >= 500
        ? "The backend is unavailable or returned a server error. Check the backend on port 8080, then try again."
        : `Request failed (${response.status})`;
    throw new Error([message || fallback, errors].filter(Boolean).join("\n"));
  }
  if (!json)
    throw new Error(
      "Unexpected API response. Check that the backend is running on port 8080.",
    );
  return json as T;
}
