import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

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
});
