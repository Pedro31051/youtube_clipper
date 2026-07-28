import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleAlert,
  Clapperboard,
  ListTodo,
  Play,
  Plus,
  RotateCcw,
  SquarePen,
  X
} from "lucide-react";

import {
  type AnalysisInput,
  type Clip,
  cancelJob,
  createAnalysis,
  exportToDrive,
  getClips,
  getJobs,
  getProject,
  getProjects,
  retryJob,
  retryPreview,
  reviewClips
} from "./api/client";
import { useJobEvents } from "./hooks/useJobEvents";
import { ClipEditor } from "./ClipEditor";
import { JobsExportPanel } from "./JobsExportPanel";
import { Button, EmptyState, SkeletonCards, StatusBadge } from "./ui";

const STATUS_LABELS: Record<string, string> = {
  proposed: "Aguardando preview",
  previewing: "Gerando preview",
  ready: "Pronto",
  approved: "Aprovado",
  rejected: "Rejeitado",
  rendering: "Renderizando",
  rendered: "Render pronto",
  exported: "Exportado",
  failed: "Falhou"
};

const FILTERS = [
  ["all", "Todos"],
  ["processing", "Processando"],
  ["ready", "Prontos"],
  ["approved", "Aprovados"],
  ["rejected", "Rejeitados"],
  ["failed", "Falhas"]
] as const;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatTime(milliseconds: number) {
  const total = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function clipMatchesFilter(clip: Clip, filter: string) {
  if (filter === "all") return true;
  if (filter === "processing") {
    return ["proposed", "previewing"].includes(clip.status);
  }
  if (filter === "ready") return clip.status === "ready";
  return clip.status === filter;
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
      <Button type="button" icon={RotateCcw} onClick={onRetry}>
        Tentar novamente
      </Button>
    </section>
  );
}

function NewAnalysis({
  busy,
  onSubmit
}: {
  busy: boolean;
  onSubmit: (input: AnalysisInput) => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState<AnalysisInput["language"]>("auto");
  const [maxClips, setMaxClips] = useState(5);
  const [targetDuration, setTargetDuration] = useState(45);
  const [aspectRatio, setAspectRatio] =
    useState<AnalysisInput["aspect_ratio"]>("9:16");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({
      name,
      url,
      language,
      max_clips: maxClips,
      target_duration_seconds: targetDuration,
      aspect_ratio: aspectRatio
    });
  }

  return (
    <section className="analysis-card" aria-labelledby="analysis-title">
      <div>
        <span className="eyebrow">Novo projeto</span>
        <h2 id="analysis-title">Transforme um vídeo em candidatos revisáveis</h2>
        <p>
          Cole a fonte, escolha o objetivo e acompanhe análise e previews sem
          sair desta tela.
        </p>
      </div>
      <form onSubmit={submit}>
        <label>
          Nome do projeto
          <input
            required
            maxLength={160}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Entrevista semanal"
          />
        </label>
        <label className="source-field">
          URL do YouTube
          <input
            required
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
          />
        </label>
        <div className="form-grid">
          <label>
            Idioma
            <select
              value={language}
              onChange={(event) =>
                setLanguage(event.target.value as AnalysisInput["language"])
              }
            >
              <option value="auto">Automático</option>
              <option value="pt">Português</option>
              <option value="en">Inglês</option>
            </select>
          </label>
          <label>
            Quantidade
            <select
              value={maxClips}
              onChange={(event) => setMaxClips(Number(event.target.value))}
            >
              {[3, 5, 8, 10].map((value) => (
                <option key={value} value={value}>
                  {value} cortes
                </option>
              ))}
            </select>
          </label>
          <label>
            Duração-alvo
            <select
              value={targetDuration}
              onChange={(event) => setTargetDuration(Number(event.target.value))}
            >
              {[30, 45, 55].map((value) => (
                <option key={value} value={value}>
                  {value} segundos
                </option>
              ))}
            </select>
          </label>
          <label>
            Formato
            <select
              value={aspectRatio}
              onChange={(event) =>
                setAspectRatio(event.target.value as AnalysisInput["aspect_ratio"])
              }
            >
              <option value="9:16">Vertical · 9:16</option>
              <option value="1:1">Quadrado · 1:1</option>
              <option value="16:9">Horizontal · 16:9</option>
            </select>
          </label>
        </div>
        <Button variant="primary" type="submit" busy={busy} icon={Clapperboard}>
          {busy ? "Criando análise…" : "Analisar vídeo"}
        </Button>
      </form>
    </section>
  );
}

function ClipCard({
  clip,
  selected,
  playing,
  busy,
  onSelect,
  onPlay,
  onDecision,
  onEdit,
  onRetryPreview
}: {
  clip: Clip;
  selected: boolean;
  playing: boolean;
  busy: boolean;
  onSelect: () => void;
  onPlay: () => void;
  onDecision: (decision: "approve" | "reject") => void;
  onEdit: () => void;
  onRetryPreview: () => void;
}) {
  const canApprove =
    clip.preview_status === "ready" &&
    ["ready", "rejected"].includes(clip.status);
  const canReject = ["proposed", "ready", "approved"].includes(clip.status);
  const summary =
    clip.suggestion.summary ??
    clip.suggestion.transcript ??
    "A análise não forneceu uma justificativa textual.";

  return (
    <article className="clip-card" data-status={clip.status}>
      <div className="clip-media">
        {playing && clip.preview_url ? (
          <video
            key={clip.preview_url}
            src={clip.preview_url}
            poster={clip.poster_url ?? undefined}
            controls
            autoPlay
            playsInline
            preload="metadata"
            aria-label={`Preview de ${clip.title}`}
          />
        ) : clip.poster_url ? (
          <button
            className="poster-button"
            type="button"
            onClick={onPlay}
            aria-label={`Reproduzir ${clip.title}`}
          >
            <img src={clip.poster_url} alt="" loading="lazy" />
            <span aria-hidden="true"><Play size={18} fill="currentColor" /></span>
          </button>
        ) : (
          <div className="media-pending">
            <span aria-hidden="true">
              {clip.status === "failed" ? <CircleAlert size={28} /> : <Clapperboard size={28} />}
            </span>
            <strong>{STATUS_LABELS[clip.status] ?? clip.status}</strong>
            {clip.status === "failed" ? (
              <Button type="button" icon={RotateCcw} onClick={onRetryPreview}>
                Tentar preview novamente
              </Button>
            ) : null}
          </div>
        )}
        <span className="score-badge">{Math.round(clip.score)} pts</span>
      </div>
      <div className="clip-content">
        <div className="clip-title-row">
          <label className="clip-check">
            <input
              type="checkbox"
              checked={selected}
              onChange={onSelect}
              aria-label={`Selecionar ${clip.title}`}
            />
          </label>
          <div>
            <span className="clip-rank">Candidato {clip.rank}</span>
            <h3>{clip.title}</h3>
          </div>
          <StatusBadge status={clip.status}>
            {STATUS_LABELS[clip.status] ?? clip.status}
          </StatusBadge>
        </div>
        <p className="clip-summary">{summary}</p>
        <div className="clip-meta">
          <span>
            {formatTime(clip.start_ms)} → {formatTime(clip.end_ms)}
          </span>
          <span>{formatTime(clip.duration_ms)} de duração</span>
          <span>versão {clip.plan_version}</span>
        </div>
        <div className="clip-actions">
          <Button
            variant="primary"
            icon={SquarePen}
            type="button"
            onClick={onEdit}
            disabled={!clip.preview_url}
          >
            Abrir editor
          </Button>
          <Button
            icon={Check}
            type="button"
            onClick={() => onDecision("approve")}
            disabled={!canApprove || busy}
          >
            Aprovar
          </Button>
          <Button
            variant="danger"
            icon={X}
            type="button"
            onClick={() => onDecision("reject")}
            disabled={!canReject || busy}
          >
            Rejeitar
          </Button>
        </div>
      </div>
    </article>
  );
}

export function App() {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [showNew, setShowNew] = useState(false);
  const [showOperations, setShowOperations] = useState(false);
  const [filter, setFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [playingId, setPlayingId] = useState<string>();
  const [editingClip, setEditingClip] = useState<Clip>();

  const projects = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  useEffect(() => {
    if (!selectedProjectId && projects.data?.length) {
      setSelectedProjectId(projects.data[0].project_id);
    }
  }, [projects.data, selectedProjectId]);

  const project = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId!),
    enabled: Boolean(selectedProjectId)
  });
  const clips = useQuery({
    queryKey: ["clips", selectedProjectId],
    queryFn: () => getClips(selectedProjectId!),
    enabled: Boolean(selectedProjectId),
    refetchInterval: (query) => {
      const values = query.state.data;
      return values?.some((clip) =>
        ["proposed", "previewing"].includes(clip.status)
      )
        ? 1_500
        : false;
    }
  });
  const jobs = useQuery({
    queryKey: ["jobs", selectedProjectId],
    queryFn: () => getJobs(selectedProjectId),
    refetchInterval: 2_000
  });
  const activeJob = jobs.data?.find((job) =>
    ["queued", "running"].includes(job.state)
  );
  const live = useJobEvents(activeJob);

  useEffect(() => {
    if (!editingClip || !clips.data) return;
    const fresh = clips.data.find(
      (clip) => clip.clip_id === editingClip.clip_id
    );
    if (fresh && fresh.updated_at !== editingClip.updated_at) {
      setEditingClip(fresh);
    }
  }, [clips.data, editingClip]);

  useEffect(() => {
    if (
      live.event?.state === "completed" ||
      live.event?.state === "failed" ||
      live.event?.state === "cancelled"
    ) {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["project", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", selectedProjectId] });
    }
  }, [live.event, queryClient, selectedProjectId]);

  const create = useMutation({
    mutationFn: createAnalysis,
    onSuccess: ({ project: createdProject }) => {
      setSelectedProjectId(createdProject.project_id);
      setShowNew(false);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  });
  const review = useMutation({
    mutationFn: ({
      clipIds,
      decision
    }: {
      clipIds: string[];
      decision: "approve" | "reject";
    }) => reviewClips(clipIds, decision),
    onSuccess: () => {
      setSelectedIds([]);
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    }
  });
  const preview = useMutation({
    mutationFn: retryPreview,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", selectedProjectId] });
    }
  });
  const cancel = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", selectedProjectId] });
    }
  });
  const retry = useMutation({
    mutationFn: retryJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", selectedProjectId] });
    }
  });
  const drive = useMutation({
    mutationFn: ({
      clipId,
      folderName,
      folderId
    }: {
      clipId: string;
      folderName: string;
      folderId?: string;
    }) => exportToDrive(clipId, folderName, folderId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["clips", selectedProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", selectedProjectId] });
    }
  });

  const visibleClips = (clips.data ?? []).filter((clip) =>
    clipMatchesFilter(clip, filter)
  );
  const error =
    projects.error ??
    project.error ??
    clips.error ??
    jobs.error ??
    create.error ??
    review.error ??
    preview.error ??
    cancel.error ??
    retry.error ??
    drive.error;

  function chooseProject(projectId: string) {
    setSelectedProjectId(projectId);
    setShowNew(false);
    setShowOperations(false);
    setSelectedIds([]);
    setPlayingId(undefined);
    setEditingClip(undefined);
  }

  function toggleClip(clipId: string) {
    setSelectedIds((current) => {
      if (current.includes(clipId)) {
        return current.filter((id) => id !== clipId);
      }
      return current.length < 20 ? [...current, clipId] : current;
    });
  }

  const title = showOperations
    ? "Jobs e exportações"
    : showNew
      ? "Nova análise"
      : project.data?.name ?? "Projetos de cortes";

  return (
    <div className={`app-shell ${showOperations ? "operations-mode" : ""}`}>
      <a className="skip-link" href="#projects">Pular para o conteúdo</a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="YouTube Clipper — início">
          <span aria-hidden="true">YC</span>
          <strong>YouTube Clipper</strong>
        </a>
        <Button
          variant="primary"
          icon={Plus}
          type="button"
          onClick={() => {
            setShowNew(true);
            setShowOperations(false);
          }}
        >
          Novo projeto
        </Button>
        <button
          className={`nav-item operation-nav ${showOperations ? "active" : ""}`}
          type="button"
          aria-current={showOperations ? "page" : undefined}
          onClick={() => {
            setShowOperations(true);
            setShowNew(false);
            setEditingClip(undefined);
          }}
        >
          <span><ListTodo size={16} aria-hidden="true" /> Jobs e exportações</span>
          <small>{jobs.data?.filter((job) => ["queued", "running"].includes(job.state)).length ?? 0}</small>
        </button>
        <nav aria-label="Projetos">
          <span className="nav-heading">Projetos recentes</span>
          {projects.data?.map((item) => (
            <button
              className={`nav-item ${item.project_id === selectedProjectId && !showNew ? "active" : ""}`}
              type="button"
              key={item.project_id}
              onClick={() => chooseProject(item.project_id)}
              aria-current={item.project_id === selectedProjectId && !showNew ? "page" : undefined}
            >
              <span>{item.name}</span>
              <small>{item.clip_count} corte(s)</small>
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span>UI-7 · Operação</span>
          <p>Jobs persistentes, exportação e falhas acionáveis.</p>
        </div>
      </aside>

      <header className="topbar">
        <div>
          <span className="eyebrow">Central de trabalho</span>
          <h1>{title}</h1>
        </div>
        <div className="connection-pill" data-state={live.connection}>
          <span aria-hidden="true" />
          {activeJob ? "Processando agora" : "API conectada"}
        </div>
      </header>

      <main className="workspace" id="projects">
        {error ? (
          <ErrorNotice
            message={error instanceof Error ? error.message : "Erro desconhecido"}
            onRetry={() => {
              create.reset();
              review.reset();
              preview.reset();
              cancel.reset();
              retry.reset();
              drive.reset();
              void projects.refetch();
              void project.refetch();
              void clips.refetch();
              void jobs.refetch();
            }}
          />
        ) : null}

        {activeJob ? (
          <section className="job-banner" aria-live="polite">
            <div>
              <span className="eyebrow">
                {activeJob.kind === "analysis" ? "Análise" : "Preview"}
              </span>
              <strong>
                {live.event?.message ?? `${activeJob.kind} em andamento`}
              </strong>
            </div>
            <progress max="100" value={live.event?.progress ?? 5}>
              {live.event?.progress ?? 5}%
            </progress>
          </section>
        ) : null}

        {showOperations ? (
          <JobsExportPanel
            jobs={jobs.data ?? []}
            clips={clips.data ?? []}
            busyJobId={
              cancel.isPending
                ? cancel.variables
                : retry.isPending
                  ? retry.variables
                  : undefined
            }
            driveBusy={drive.isPending}
            onCancel={(jobId) => cancel.mutate(jobId)}
            onRetry={(jobId) => retry.mutate(jobId)}
            onDrive={(clipId, folderName, folderId) =>
              drive.mutate({ clipId, folderName, folderId })
            }
          />
        ) : showNew || (!projects.isPending && !projects.data?.length) ? (
          <NewAnalysis
            busy={create.isPending}
            onSubmit={(input) => create.mutate(input)}
          />
        ) : (
          <>
            <section className="review-header">
              <div>
                <span className="eyebrow">Revisão de cortes</span>
                <h2>{project.data?.name ?? "Carregando projeto…"}</h2>
                <p>
                  Assista aos candidatos, registre sua decisão e leve apenas os
                  melhores para o editor.
                </p>
              </div>
              <dl className="metrics">
                <div>
                  <dt>Candidatos</dt>
                  <dd>{clips.data?.length ?? "—"}</dd>
                </div>
                <div>
                  <dt>Aprovados</dt>
                  <dd>
                    {clips.data?.filter((clip) => clip.status === "approved")
                      .length ?? "—"}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="review-toolbar" aria-label="Filtros da revisão">
              <div className="filters">
                {FILTERS.map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={filter === value ? "active" : ""}
                    onClick={() => setFilter(value)}
                  >
                    {label}
                    <span>
                      {(clips.data ?? []).filter((clip) =>
                        clipMatchesFilter(clip, value)
                      ).length}
                    </span>
                  </button>
                ))}
              </div>
              <span>{selectedIds.length}/20 selecionados</span>
            </section>

            {clips.isPending ? (
              <SkeletonCards aria-label="Carregando cortes" />
            ) : visibleClips.length ? (
              <section className="clip-grid" aria-label="Candidatos de corte">
                {visibleClips.map((clip) => (
                  <ClipCard
                    key={clip.clip_id}
                    clip={clip}
                    selected={selectedIds.includes(clip.clip_id)}
                    playing={playingId === clip.clip_id}
                    busy={review.isPending}
                    onSelect={() => toggleClip(clip.clip_id)}
                    onPlay={() => setPlayingId(clip.clip_id)}
                    onDecision={(decision) =>
                      review.mutate({ clipIds: [clip.clip_id], decision })
                    }
                    onEdit={() => setEditingClip(clip)}
                    onRetryPreview={() => preview.mutate(clip.clip_id)}
                  />
                ))}
              </section>
            ) : (
              <EmptyState
                title="Nenhum corte neste filtro"
                description={
                  clips.data?.length
                    ? "Escolha outro status para continuar a revisão."
                    : "A análise ainda não produziu candidatos. Acompanhe a atividade acima."
                }
              />
            )}
          </>
        )}
      </main>

      <aside className="inspector" aria-labelledby="inspector-title">
        <span className="eyebrow">Inspetor</span>
        {editingClip ? (
          <>
            <h2 id="inspector-title">{editingClip.title}</h2>
            <StatusBadge status={editingClip.status}>
              {STATUS_LABELS[editingClip.status] ?? editingClip.status}
            </StatusBadge>
            <dl className="inspector-details">
              <div>
                <dt>Intervalo</dt>
                <dd>
                  {formatTime(editingClip.start_ms)} →{" "}
                  {formatTime(editingClip.end_ms)}
                </dd>
              </div>
              <div>
                <dt>Plano</dt>
                <dd>versão {editingClip.plan_version}</dd>
              </div>
              <div>
                <dt>Identidade</dt>
                <dd>{editingClip.clip_id}</dd>
              </div>
            </dl>
            <div className="editor-boundary">
              <strong>Editor compacto disponível</strong>
              <p>
                Abra a superfície completa para corte fino, waveform, layout,
                áudio, editorial e saída.
              </p>
            </div>
          </>
        ) : (
          <>
            <h2 id="inspector-title">Selecione “Abrir editor”</h2>
            <p>
              O candidato escolhido aparece aqui com seu plano e identidade
              persistentes.
            </p>
          </>
        )}
      </aside>

      {selectedIds.length ? (
        <div className="batch-bar" role="region" aria-label="Ações em lote">
          <strong>{selectedIds.length} corte(s) selecionado(s)</strong>
          <Button
            icon={Check}
            type="button"
            onClick={() =>
              review.mutate({ clipIds: selectedIds, decision: "approve" })
            }
            disabled={review.isPending}
          >
            Aprovar selecionados
          </Button>
          <Button
            variant="danger"
            icon={X}
            type="button"
            onClick={() =>
              review.mutate({ clipIds: selectedIds, decision: "reject" })
            }
            disabled={review.isPending}
          >
            Rejeitar selecionados
          </Button>
          <Button variant="ghost" type="button" onClick={() => setSelectedIds([])}>
            Limpar
          </Button>
        </div>
      ) : null}
      {editingClip ? (
        <ClipEditor
          clip={editingClip}
          onClose={() => {
            setEditingClip(undefined);
            void clips.refetch();
            void jobs.refetch();
          }}
          onUpdated={(updated) => {
            setEditingClip(updated);
            queryClient.setQueryData<Clip[]>(
              ["clips", selectedProjectId],
              (current) =>
                current?.map((item) =>
                  item.clip_id === updated.clip_id ? updated : item
                )
            );
          }}
        />
      ) : null}
    </div>
  );
}
