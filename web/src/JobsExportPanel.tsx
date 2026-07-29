import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Ban,
  Clock3,
  Download,
  ExternalLink,
  FileJson,
  FolderUp,
  Gauge,
  RefreshCw,
  X
} from "lucide-react";

import {
  type Clip,
  type Job,
  finalDownloadUrl,
  jobReportUrl
} from "./api/client";
import { Button, EmptyState, StatusBadge } from "./ui";

const KIND_LABELS: Record<string, string> = {
  analysis: "Análise",
  preview: "Preview",
  render: "Render final",
  drive_upload: "Google Drive"
};

const STATE_LABELS: Record<string, string> = {
  queued: "Na fila",
  running: "Em andamento",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
  interrupted: "Interrompido"
};

const TERMINAL_STATES = ["completed", "failed", "cancelled", "interrupted"];
const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function duration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return "Calculando";
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes} min ${remainder.toString().padStart(2, "0")} s`;
}

function jobStageLabel(job: Job) {
  if (job.state === "cancelled") return "Cancelado";
  if (job.state === "interrupted") return "Interrompido";
  if (job.state === "failed") return "Falhou";
  if (job.state === "completed") return job.stage ?? "Concluído";
  return job.stage ?? (job.state === "queued" ? "Fila" : "Processando");
}

function JobTiming({ job, now }: { job: Job; now: number }) {
  const created = Date.parse(job.created_at);
  const terminal = TERMINAL_STATES.includes(job.state);
  const eventTime = job.event_timestamp_ms ?? Date.parse(job.updated_at);
  const elapsed = Math.max(0, ((terminal ? eventTime : now) - created) / 1000);
  const progress = Number(job.progress ?? 0);
  const remaining =
    !terminal && progress > 0
      ? elapsed * ((100 - progress) / progress)
      : terminal
        ? 0
        : null;

  return (
    <dl className="job-timing">
      <div><dt><Clock3 size={13} /> Tempo</dt><dd>{duration(elapsed)}</dd></div>
      <div><dt><Gauge size={13} /> Estimativa</dt><dd>{duration(remaining)}</dd></div>
    </dl>
  );
}

function ExportDialog({
  clip,
  busy,
  onClose,
  onDrive
}: {
  clip: Clip;
  busy: boolean;
  onClose: () => void;
  onDrive: (folderName: string, folderId?: string) => void;
}) {
  const [folderName, setFolderName] = useState("YouTube_Clips");
  const [folderId, setFolderId] = useState("");
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.querySelector<HTMLElement>("#export-dialog-close")?.focus();

    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE)
      ).filter(
        (element) =>
          element.getAttribute("aria-hidden") !== "true" &&
          !element.hasAttribute("disabled")
      );
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1)!;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", keyboard);
    return () => {
      window.removeEventListener("keydown", keyboard);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [clip.clip_id]);

  return (
    <div className="dialog-backdrop">
      <section
        ref={dialogRef}
        className="export-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        tabIndex={-1}
      >
        <header>
          <div>
            <span className="eyebrow">Entrega validada</span>
            <h2 id="export-dialog-title">Exportar “{clip.title}”</h2>
          </div>
          <Button id="export-dialog-close" variant="ghost" icon={X} aria-label="Fechar exportação" onClick={() => onCloseRef.current()}>
            Fechar
          </Button>
        </header>
        <div className="export-options">
          <article>
            <Download size={20} aria-hidden="true" />
            <div><strong>Baixar localmente</strong><p>MP4 final, transmitido sem carregar o arquivo inteiro na memória.</p></div>
            <a className="ui-button ui-button-primary" href={finalDownloadUrl(clip.clip_id)} download>
              <Download size={16} aria-hidden="true" /><span>Baixar MP4</span>
            </a>
          </article>
          <article>
            <FolderUp size={20} aria-hidden="true" />
            <div><strong>Enviar ao Google Drive</strong><p>O upload entra na fila e continua visível nesta tela.</p></div>
            <label>Nome da pasta<input value={folderName} onChange={(event) => setFolderName(event.target.value)} /></label>
            <label>ID da pasta <span>(opcional)</span><input value={folderId} onChange={(event) => setFolderId(event.target.value)} /></label>
            <Button variant="primary" icon={FolderUp} busy={busy} disabled={!folderName.trim()} onClick={() => onDrive(folderName.trim(), folderId)}>
              Enviar ao Drive
            </Button>
          </article>
        </div>
      </section>
    </div>
  );
}

export function JobsExportPanel({
  jobs,
  clips,
  busyJobId,
  driveBusy,
  onCancel,
  onRetry,
  onDrive
}: {
  jobs: Job[];
  clips: Clip[];
  busyJobId?: string;
  driveBusy: boolean;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onDrive: (clipId: string, folderName: string, folderId?: string) => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [exportClip, setExportClip] = useState<Clip>();
  const closeExport = useCallback(() => setExportClip(undefined), []);
  const clipById = useMemo(
    () => new Map(clips.map((clip) => [clip.clip_id, clip])),
    [clips]
  );
  const deliverables = clips.filter(
    (clip) =>
      ["rendered", "exported"].includes(clip.status) &&
      clip.assets?.some((asset) => asset.kind === "render" && asset.valid)
  );

  const hasActiveJobs = jobs.some((job) =>
    ["queued", "running"].includes(job.state)
  );
  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs]);

  return (
    <section className="operations" aria-labelledby="operations-title">
      <header className="operations-header">
        <div>
          <span className="eyebrow">Operação rastreável</span>
          <h2 id="operations-title">Jobs e exportações</h2>
          <p>Acompanhe cada execução, resolva falhas e entregue somente renders físicos válidos.</p>
        </div>
        <div className="queue-summary">
          <strong>{jobs.filter((job) => ["queued", "running"].includes(job.state)).length}</strong>
          <span>na fila agora</span>
        </div>
      </header>

      <section className="deliverables" aria-labelledby="deliverables-title">
        <div className="section-heading">
          <div><span className="eyebrow">Saídas</span><h3 id="deliverables-title">Prontas para entrega</h3></div>
          <span>{deliverables.length} arquivo(s)</span>
        </div>
        {deliverables.length ? (
          <div className="deliverable-grid">
            {deliverables.map((clip) => (
              <article key={clip.clip_id}>
                <div>
                  <StatusBadge status={clip.status}>{clip.status === "exported" ? "Exportado" : "Render pronto"}</StatusBadge>
                  <h4>{clip.title}</h4>
                  <p>Plano v{clip.plan_version} · {Math.round(clip.score)} pontos</p>
                </div>
                <Button variant="primary" icon={ExternalLink} onClick={() => setExportClip(clip)}>Exportar</Button>
              </article>
            ))}
          </div>
        ) : (
          <p className="inline-empty">Conclua um render final aprovado para habilitar download e Drive.</p>
        )}
      </section>

      <section className="job-history" aria-labelledby="job-history-title">
        <div className="section-heading">
          <div><span className="eyebrow">Histórico persistente</span><h3 id="job-history-title">Fila e execuções</h3></div>
          <span>{jobs.length} job(s)</span>
        </div>
        {jobs.length ? (
          <div className="job-list">
            {jobs.map((job) => {
              const clip = job.clip_id ? clipById.get(job.clip_id) : undefined;
              const active = ["queued", "running"].includes(job.state);
              const retryable = ["failed", "cancelled", "interrupted"].includes(job.state);
              return (
                <article className="job-card" key={job.job_id} data-state={job.state}>
                  <header>
                    <div>
                      <span className="job-kind">{KIND_LABELS[job.kind] ?? job.kind}</span>
                      <h4>{clip?.title ?? "Projeto sem corte associado"}</h4>
                      <details>
                        <summary>Detalhes técnicos</summary>
                        <code>{job.job_id}</code>
                      </details>
                    </div>
                    <StatusBadge status={job.state}>{STATE_LABELS[job.state] ?? job.state}</StatusBadge>
                  </header>
                  <progress max="100" value={Number(job.progress ?? 0)}>{job.progress}%</progress>
                  <div className="job-stage">
                    <span>{jobStageLabel(job)}</span>
                    <strong>{Number(job.progress ?? 0)}%</strong>
                  </div>
                  <JobTiming job={job} now={now} />
                  <div className="job-log" aria-label={`Logs de ${job.job_id}`}>
                    {(job.events ?? []).slice(-3).map((event) => (
                      <p key={event.seq}><span>{event.progress}%</span>{event.message}</p>
                    ))}
                    {!job.events?.length && job.message ? <p><span>{job.progress}%</span>{job.message}</p> : null}
                  </div>
                  {job.error || job.action ? (
                    <div className="job-guidance" role="alert">
                      <strong>{job.message ?? "A execução falhou"}</strong>
                      {job.action ? <p>{job.action}</p> : null}
                      {job.error ? <details><summary>Detalhe técnico</summary><code>{job.error}</code></details> : null}
                    </div>
                  ) : null}
                  <footer>
                    {active ? (
                      <Button variant="danger" icon={Ban} busy={busyJobId === job.job_id} onClick={() => onCancel(job.job_id)}>Cancelar</Button>
                    ) : null}
                    {retryable ? (
                      <Button icon={RefreshCw} busy={busyJobId === job.job_id} onClick={() => onRetry(job.job_id)}>Tentar novamente</Button>
                    ) : null}
                    <a className="ui-button ui-button-ghost" href={jobReportUrl(job.job_id)} download>
                      <FileJson size={16} aria-hidden="true" /><span>Relatório</span>
                    </a>
                  </footer>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyState title="Nenhum job registrado" description="Inicie uma análise para criar o primeiro item da fila." />
        )}
      </section>

      {exportClip ? (
        <ExportDialog
          clip={exportClip}
          busy={driveBusy}
          onClose={closeExport}
          onDrive={(folderName, folderId) => onDrive(exportClip.clip_id, folderName, folderId)}
        />
      ) : null}
    </section>
  );
}
