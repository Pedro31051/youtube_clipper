import type { components } from "./schema";

export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type Project = ProjectSummary & {
  sources: Array<{ source_id: string; kind: string; uri: string }>;
};
export type Clip = {
  clip_id: string;
  project_id: string;
  rank: number;
  title: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  score: number;
  status: string;
  plan_version: number;
  updated_at?: string;
  preview_status: string;
  preview_url?: string | null;
  poster_url?: string | null;
  edit_plan: EditPlan;
  assets?: Array<{
    asset_id: string;
    kind: string;
    url: string;
    valid: boolean;
  }>;
  suggestion: {
    summary?: string;
    transcript?: string;
    hashtags?: string[];
  };
};
export type EditPlan = {
  schema_version: string;
  plan_version: number;
  clip_id: string;
  source_id: string;
  timeline: { start_ms: number; end_ms: number; duration_ms: number };
  layout: {
    mode: "crop_center" | "blur_background" | "split_blur";
    crop_focus?: "left" | "center" | "right";
    blur_sigma?: number;
    overlay_position?: "top" | "bottom";
  };
  captions: {
    enabled: boolean;
    theme?: "classic" | "solid" | "highlight";
    position?: "bottom" | "center" | "top";
  };
  audio: {
    include_source: boolean;
    normalize?: boolean;
    narration_type?: "none" | "external";
    narration_path?: string | null;
  };
  editorial: {
    overlay_enabled?: boolean;
    overlay_text?: string | null;
    template_variant?: "variant_default" | "variant_news" | "variant_impact";
  };
  output: {
    aspect_ratio: "9:16" | "1:1" | "16:9";
    resolution?: "720x1280" | "1080x1920" | "1080x1080" | "1920x1080";
  };
};
export type Job = Record<string, unknown> & {
  job_id: string;
  kind: string;
  state: string;
  project_id: string;
  updated_at: string;
  error?: string | null;
};
export type AnalysisInput = {
  name: string;
  url: string;
  language: "auto" | "pt" | "en";
  max_clips: number;
  target_duration_seconds: number;
  aspect_ratio: "9:16" | "1:1" | "16:9";
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

async function requestJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers
    }
  });
  if (!response.ok) {
    let message = `A API respondeu com HTTP ${response.status}.`;
    try {
      const payload = (await response.json()) as {
        error?: string;
        detail?: string | Array<{ msg: string }>;
      };
      if (payload.error) message = payload.error;
      else if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg).join(" ");
      }
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

export async function getProject(projectId: string): Promise<Project> {
  const payload = await requestJson<{ project: Project }>(
    `/api/v1/projects/${encodeURIComponent(projectId)}`
  );
  return payload.project;
}

export async function getClips(projectId: string): Promise<Clip[]> {
  const payload = await requestJson<{ clips: Clip[] }>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/clips`
  );
  return payload.clips;
}

export async function getJobs(projectId?: string): Promise<Job[]> {
  const query = projectId
    ? `?limit=50&project_id=${encodeURIComponent(projectId)}`
    : "?limit=20";
  const payload = await requestJson<JobsResponse>(`/api/v1/jobs${query}`);
  return payload.jobs as Job[];
}

export async function createAnalysis(input: AnalysisInput): Promise<{
  project: Project;
  job: Job;
}> {
  const projectPayload = await requestJson<{ project: Project }>(
    "/api/v1/projects",
    {
      method: "POST",
      body: JSON.stringify({
        name: input.name,
        source: { kind: "youtube", uri: input.url }
      })
    }
  );
  const jobPayload = await requestJson<{ job: Job }>(
    `/api/v1/projects/${encodeURIComponent(projectPayload.project.project_id)}/analysis-jobs`,
    {
      method: "POST",
      body: JSON.stringify({
        language: input.language,
        max_clips: input.max_clips,
        target_duration_seconds: input.target_duration_seconds,
        aspect_ratio: input.aspect_ratio
      })
    }
  );
  return { project: projectPayload.project, job: jobPayload.job };
}

export async function reviewClips(
  clipIds: string[],
  decision: "approve" | "reject"
): Promise<Clip[]> {
  const payload = await requestJson<{ clips: Clip[] }>("/api/v1/clips/review", {
    method: "POST",
    body: JSON.stringify({ clip_ids: clipIds, decision })
  });
  return payload.clips;
}

export async function retryPreview(clipId: string): Promise<Job> {
  const payload = await requestJson<{ job: Job }>(
    `/api/v1/clips/${encodeURIComponent(clipId)}/preview-jobs`,
    { method: "POST" }
  );
  return payload.job;
}

export async function updateEditPlan(
  clipId: string,
  plan: EditPlan,
  expectedPlanVersion: number
): Promise<Clip> {
  const payload = await requestJson<{ clip: Clip }>(
    `/api/v1/clips/${encodeURIComponent(clipId)}/edit-plan`,
    {
      method: "PUT",
      body: JSON.stringify({
        expected_plan_version: expectedPlanVersion,
        start_ms: plan.timeline.start_ms,
        end_ms: plan.timeline.end_ms,
        layout: plan.layout,
        captions: plan.captions,
        audio: plan.audio,
        editorial: plan.editorial,
        output: plan.output
      })
    }
  );
  return payload.clip;
}

export async function renderFinal(
  clipId: string,
  currentStatus: string
): Promise<Job> {
  if (currentStatus !== "approved") {
    await reviewClips([clipId], "approve");
  }
  const payload = await requestJson<{ job: Job }>(
    `/api/v1/clips/${encodeURIComponent(clipId)}/render-jobs`,
    { method: "POST" }
  );
  return payload.job;
}
