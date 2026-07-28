import { useQuery } from "@tanstack/react-query";

import { getJobs, getProjects } from "./api/client";
import { useJobEvents } from "./hooks/useJobEvents";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function ErrorNotice({
  message,
  onRetry
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <section className="notice notice-error" role="alert">
      <div>
        <strong>Não foi possível carregar a central</strong>
        <p>{message}</p>
      </div>
      <button type="button" onClick={onRetry}>
        Tentar novamente
      </button>
    </section>
  );
}

export function App() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: getJobs,
    refetchInterval: 5_000
  });
  const activeJob = jobs.data?.find((job) =>
    ["queued", "running"].includes(job.state)
  );
  const live = useJobEvents(activeJob);
  const error = projects.error ?? jobs.error;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="YouTube Clipper — início">
          <span aria-hidden="true">YC</span>
          <strong>YouTube Clipper</strong>
        </a>
        <nav aria-label="Navegação principal">
          <a className="nav-item active" href="#projects" aria-current="page">
            Projetos
          </a>
          <a className="nav-item" href="#activity">
            Atividade
          </a>
          <span className="nav-item disabled" aria-disabled="true">
            Configurações
          </span>
        </nav>
        <div className="sidebar-note">
          <span>Fundação UI-3</span>
          <p>Revisão e editor entram nas próximas etapas.</p>
        </div>
      </aside>

      <header className="topbar">
        <div>
          <span className="eyebrow">Central de trabalho</span>
          <h1>Projetos de cortes</h1>
        </div>
        <div className="connection-pill" data-state={live.connection}>
          <span aria-hidden="true" />
          {live.connection === "live" ? "Eventos ao vivo" : "API conectada"}
        </div>
      </header>

      <main className="workspace" id="projects">
        {error ? (
          <ErrorNotice
            message={error instanceof Error ? error.message : "Erro desconhecido"}
            onRetry={() => {
              void projects.refetch();
              void jobs.refetch();
            }}
          />
        ) : null}

        <section className="overview" aria-labelledby="overview-title">
          <div>
            <span className="eyebrow">Visão geral</span>
            <h2 id="overview-title">Continue de onde parou</h2>
            <p>
              Projetos e jobs vêm da API persistente. Nenhum estado desta tela
              depende da string Python do painel legado.
            </p>
          </div>
          <dl className="metrics">
            <div>
              <dt>Projetos</dt>
              <dd>{projects.data?.length ?? "—"}</dd>
            </div>
            <div>
              <dt>Jobs recentes</dt>
              <dd>{jobs.data?.length ?? "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="panel project-panel" aria-labelledby="projects-title">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Workspace</span>
              <h2 id="projects-title">Projetos recentes</h2>
            </div>
            <span className="phase-label">Somente leitura na UI-3</span>
          </div>

          {projects.isPending ? (
            <div className="skeleton-list" aria-label="Carregando projetos">
              <span />
              <span />
              <span />
            </div>
          ) : projects.data?.length ? (
            <ul className="project-list">
              {projects.data.map((project) => (
                <li key={project.project_id}>
                  <div className="project-mark" aria-hidden="true">
                    {project.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="project-copy">
                    <strong>{project.name}</strong>
                    <span>
                      Atualizado {formatDate(project.updated_at)} ·{" "}
                      {project.clip_count} corte(s)
                    </span>
                  </div>
                  <span className="status-badge">{project.status}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">
              <span className="empty-index">01</span>
              <h3>Nenhum projeto persistido</h3>
              <p>
                A criação e análise guiadas chegam na UI-4. Por enquanto, esta
                tela confirma a conexão React ↔ FastAPI ↔ SQLite.
              </p>
            </div>
          )}
        </section>

        <section className="panel activity-panel" id="activity">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">SSE</span>
              <h2>Atividade operacional</h2>
            </div>
            <span className="phase-label">{live.connection}</span>
          </div>
          {activeJob ? (
            <div className="job-progress" aria-live="polite">
              <div className="job-progress-copy">
                <strong>{live.event?.message ?? `${activeJob.kind} em andamento`}</strong>
                <span>{activeJob.job_id}</span>
              </div>
              <progress max="100" value={live.event?.progress ?? 0}>
                {live.event?.progress ?? 0}%
              </progress>
            </div>
          ) : (
            <p className="quiet-state">Nenhum job ativo neste momento.</p>
          )}
        </section>
      </main>

      <aside className="inspector" aria-labelledby="inspector-title">
        <span className="eyebrow">Inspetor</span>
        <h2 id="inspector-title">Nada selecionado</h2>
        <p>
          Selecione um projeto ou corte quando a revisão for habilitada na UI-4.
        </p>
        <div className="inspector-placeholder" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </aside>
    </div>
  );
}
