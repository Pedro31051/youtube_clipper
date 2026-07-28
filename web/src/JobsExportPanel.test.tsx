import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JobsExportPanel } from "./JobsExportPanel";
import type { Clip, Job } from "./api/client";

const clip = {
  clip_id: "clp_11111111111111111111111111111111",
  project_id: "prj_11111111111111111111111111111111",
  rank: 1,
  title: "Entrega aprovada",
  start_ms: 0,
  end_ms: 3000,
  duration_ms: 3000,
  score: 95,
  status: "rendered",
  plan_version: 2,
  preview_status: "ready",
  edit_plan: {} as Clip["edit_plan"],
  assets: [
    {
      asset_id: "ast_11111111111111111111111111111111",
      kind: "render",
      url: "/render",
      valid: true
    }
  ],
  suggestion: {}
} satisfies Clip;

const failedJob = {
  job_id: "job_11111111111111111111111111111111",
  project_id: clip.project_id,
  clip_id: clip.clip_id,
  kind: "drive_upload",
  state: "failed",
  attempt: 1,
  progress: 100,
  message: "O Google Drive recusou o envio.",
  action: "Configure OAuth e tente novamente.",
  error: "quota exceeded",
  created_at: "2026-07-28T10:00:00Z",
  updated_at: "2026-07-28T10:00:10Z",
  event_timestamp_ms: Date.parse("2026-07-28T10:00:10Z"),
  events: []
} satisfies Job;

describe("UI-7 jobs and exports", () => {
  it("keeps failure guidance, retry and report visible", () => {
    const retry = vi.fn();
    render(
      <JobsExportPanel
        jobs={[failedJob]}
        clips={[clip]}
        driveBusy={false}
        onCancel={vi.fn()}
        onRetry={retry}
        onDrive={vi.fn()}
      />
    );

    expect(screen.getByText("Configure OAuth e tente novamente.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(retry).toHaveBeenCalledWith(failedJob.job_id);
    expect(screen.getByRole("link", { name: "Relatório" })).toHaveAttribute(
      "href",
      `/api/v1/jobs/${failedJob.job_id}/report`
    );
  });

  it("opens a safe export dialog only for a valid render", () => {
    const drive = vi.fn();
    render(
      <JobsExportPanel
        jobs={[]}
        clips={[clip]}
        driveBusy={false}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
        onDrive={drive}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Exportar" }));
    expect(screen.getByRole("dialog", { name: /Exportar/ })).toBeVisible();
    expect(screen.getByRole("link", { name: "Baixar MP4" })).toHaveAttribute(
      "href",
      `/api/v1/clips/${clip.clip_id}/export/download`
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar ao Drive" }));
    expect(drive).toHaveBeenCalledWith(
      clip.clip_id,
      "YouTube_Clips",
      ""
    );
  });
});
