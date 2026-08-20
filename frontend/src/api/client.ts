import type { paths } from "./schema";

export type BackendPaths = paths;

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/$/, "");

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`API request failed with status ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function getJson(
  path: (keyof BackendPaths & string) | "/openapi.json",
): Promise<unknown> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiRequestError(response.status);
  }

  return response.json() as Promise<unknown>;
}