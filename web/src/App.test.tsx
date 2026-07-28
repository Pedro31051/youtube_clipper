import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("wavesurfer.js", () => ({
  default: {
    create: () => ({ on: vi.fn(), destroy: vi.fn() })
  }
}));
vi.mock("wavesurfer.js/dist/plugins/regions.esm.js", () => ({
  default: {
    create: () => ({ on: vi.fn(), addRegion: vi.fn() })
  }
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  );
}

describe("UI-3 shell", () => {
  it("renders persisted projects from the generated API contract", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/jobs")) {
        return new Response(JSON.stringify({ success: true, jobs: [] }), {
          status: 200
        });
      }
      return new Response(
        JSON.stringify({
          success: true,
          projects: [
            {
              project_id: "prj_00000000000000000000000000000000",
              name: "Entrevista semanal",
              status: "active",
              created_at: "2026-07-28T00:00:00Z",
              updated_at: "2026-07-28T10:00:00Z",
              clip_count: 3,
              job_count: 1
            }
          ]
        }),
        { status: 200 }
      );
    });

    renderApp();

    expect(await screen.findByText("Entrevista semanal")).toBeInTheDocument();
    expect(screen.getByText("3 corte(s)", { exact: false })).toBeInTheDocument();
  });

  it("keeps an actionable API error visible", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "SQLite indisponível" }), {
        status: 503
      })
    );

    renderApp();

    expect(
      await screen.findByText("Não foi possível carregar a central")
    ).toBeInTheDocument();
    expect(screen.getByText("SQLite indisponível")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Tentar novamente" })
    ).toBeInTheDocument();
  });

  it("reviews a clip by immutable identity with an on-demand player", async () => {
    const project = {
      project_id: "prj_00000000000000000000000000000000",
      name: "Entrevista semanal",
      status: "review",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-28T10:00:00Z",
      clip_count: 1,
      job_count: 4,
      sources: [
        {
          source_id: "src_00000000000000000000000000000000",
          kind: "youtube",
          uri: "https://www.youtube.com/watch?v=fixture"
        }
      ]
    };
    const clip = {
      clip_id: "clp_11111111111111111111111111111111",
      project_id: project.project_id,
      rank: 1,
      title: "A pergunta decisiva",
      start_ms: 3000,
      end_ms: 9000,
      duration_ms: 6000,
      score: 94,
      status: "ready",
      plan_version: 1,
      preview_status: "ready",
      preview_url:
        "/api/v1/assets/ast_11111111111111111111111111111111?v=1",
      poster_url:
        "/api/v1/assets/ast_22222222222222222222222222222222?v=1",
      edit_plan: {
        schema_version: "1.0.0",
        plan_version: 1,
        clip_id: "clp_11111111111111111111111111111111",
        source_id: "src_00000000000000000000000000000000",
        timeline: { start_ms: 3000, end_ms: 9000, duration_ms: 6000 },
        layout: { mode: "blur_background" },
        captions: { enabled: false, theme: "classic", position: "bottom" },
        audio: { include_source: true, normalize: true },
        editorial: {
          overlay_enabled: false,
          overlay_text: null,
          template_variant: "variant_default"
        },
        output: { aspect_ratio: "9:16", resolution: "1080x1920" }
      },
      suggestion: { summary: "Resposta curta e autossuficiente." }
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input, init) => {
        const url = String(input);
        if (url === "/api/v1/projects") {
          return new Response(JSON.stringify({ success: true, projects: [project] }));
        }
        if (url.includes("/clips/review")) {
          const body = JSON.parse(String(init?.body)) as {
            clip_ids: string[];
            decision: string;
          };
          expect(body).toEqual({
            clip_ids: [clip.clip_id],
            decision: "approve"
          });
          return new Response(
            JSON.stringify({
              success: true,
              clips: [{ ...clip, status: "approved" }]
            })
          );
        }
        if (url.includes("/clips")) {
          return new Response(JSON.stringify({ success: true, clips: [clip] }));
        }
        if (url.includes("/jobs")) {
          return new Response(JSON.stringify({ success: true, jobs: [] }));
        }
        if (url.includes(`/projects/${project.project_id}`)) {
          return new Response(JSON.stringify({ success: true, project }));
        }
        throw new Error(`Unexpected request: ${url}`);
      });

    renderApp();

    expect(await screen.findByText("A pergunta decisiva")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Preview de A pergunta decisiva")
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Reproduzir A pergunta decisiva" })
    );
    expect(
      screen.getByLabelText("Preview de A pergunta decisiva")
    ).toHaveAttribute("src", clip.preview_url);

    fireEvent.click(screen.getByRole("button", { name: "Abrir editor" }));
    expect(screen.getByText("O player mostra o último preview físico.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(clip.clip_id)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Aprovar" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/clips/review")
        )
      ).toBe(true)
    );
  });

  it("creates a project and starts analysis from the guided form", async () => {
    const project = {
      project_id: "prj_22222222222222222222222222222222",
      name: "Novo episódio",
      status: "analyzing",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-28T00:00:00Z",
      clip_count: 0,
      job_count: 1,
      sources: []
    };
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(url);
      if (url === "/api/v1/projects" && !init?.method) {
        return new Response(JSON.stringify({ success: true, projects: [] }));
      }
      if (url === "/api/v1/projects") {
        return new Response(JSON.stringify({ success: true, project }), {
          status: 201
        });
      }
      if (url.includes("/analysis-jobs")) {
        return new Response(
          JSON.stringify({
            success: true,
            job: {
              job_id: "job_22222222222222222222222222222222",
              kind: "analysis",
              state: "queued",
              project_id: project.project_id,
              updated_at: project.updated_at
            }
          }),
          { status: 202 }
        );
      }
      if (url.includes("/jobs")) {
        return new Response(JSON.stringify({ success: true, jobs: [] }));
      }
      return new Response(JSON.stringify({ success: true, projects: [] }));
    });

    renderApp();
    fireEvent.change(await screen.findByLabelText("Nome do projeto"), {
      target: { value: "Novo episódio" }
    });
    fireEvent.change(screen.getByLabelText("URL do YouTube"), {
      target: { value: "https://www.youtube.com/watch?v=fixture" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Analisar vídeo" }));

    await waitFor(() =>
      expect(calls.some((url) => url.includes("/analysis-jobs"))).toBe(true)
    );
  });
});
