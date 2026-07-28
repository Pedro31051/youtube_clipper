import type { components } from "./schema";

export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type Job = Record<string, unknown> & {
  job_id: string;
  kind: string;
  state: string;
  project_id: string;
  updated_at: string;
  error?: string | null;
};

type ProjectsResponse = components["schemas"]["ProjectsResponse"];
type JobsResponse = components["schemas"]["JobsResponse"];

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" }
  });
  if (!response.ok) {
    let message = `A API respondeu com HTTP ${response.status}.`;
    try {
      const payload = (await response.json()) as { error?: string };
      if (payload.error) message = payload.error;
    } catch {
      // The status code remains actionable when a proxy returned non-JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export async function getProjects(): Promise<ProjectSummary[]> {
  const payload = await requestJson<ProjectsResponse>("/api/v1/projects");
  return payload.projects;
}

export async function getJobs(): Promise<Job[]> {
  const payload = await requestJson<JobsResponse>("/api/v1/jobs?limit=12");
  return payload.jobs as Job[];
}
