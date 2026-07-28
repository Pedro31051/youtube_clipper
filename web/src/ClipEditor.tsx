import { useEffect, useState } from "react";
import {
  Check,
  ChevronLeft,
  Film,
  Redo2,
  RefreshCw,
  Undo2
} from "lucide-react";

import {
  type Clip,
  renderFinal,
  retryPreview,
  updateEditPlan
} from "./api/client";
import { useEditorStore } from "./editorStore";
import { WaveformEditor } from "./WaveformEditor";

const TABS = ["Corte", "Layout", "Legendas", "Áudio", "Editorial", "Saída"] as const;
type Tab = (typeof TABS)[number];

export function ClipEditor({
  clip,
  onClose,
  onUpdated
}: {
  clip: Clip;
  onClose: () => void;
  onUpdated: (clip: Clip) => void;
}) {
  const [tab, setTab] = useState<Tab>("Corte");
  const [action, setAction] = useState<"preview" | "render">();
  const {
    plan,
    serverVersion,
    past,
    future,
    sync,
    error,
    initialize,
    change,
    undo,
    redo,
    saving,
    saved,
    failed
  } = useEditorStore();

  useEffect(() => initialize(clip.clip_id, clip.edit_plan), [clip.clip_id]);

  useEffect(() => {
    if (!plan || sync !== "dirty") return;
    const timer = window.setTimeout(async () => {
      saving();
      try {
        const updated = await updateEditPlan(
          clip.clip_id,
          plan,
          serverVersion
        );
        saved(updated.edit_plan, updated.plan_version);
        onUpdated(updated);
      } catch (reason) {
        failed(reason instanceof Error ? reason.message : "Falha ao salvar");
      }
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [plan, sync, serverVersion, clip.clip_id]);

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === "z") {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
      }
      if (event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [undo, redo]);

  if (!plan) return null;
  const stale = clip.preview_status !== "ready" || sync !== "synced";

  async function regenerate() {
    setAction("preview");
    try {
      await retryPreview(clip.clip_id);
    } catch (reason) {
      failed(reason instanceof Error ? reason.message : "Falha ao gerar preview");
    } finally {
      setAction(undefined);
    }
  }

  async function render() {
    setAction("render");
    try {
      await renderFinal(clip.clip_id, clip.status);
    } catch (reason) {
      failed(reason instanceof Error ? reason.message : "Falha no render final");
    } finally {
      setAction(undefined);
    }
  }

  return (
    <div className="editor-overlay">
      <header className="editor-topbar">
        <button type="button" onClick={onClose} aria-label="Voltar à revisão">
          <ChevronLeft size={18} /> Revisão
        </button>
        <div>
          <strong>{clip.title}</strong>
          <span>{clip.clip_id}</span>
        </div>
        <div className="editor-history">
          <button type="button" onClick={undo} disabled={!past.length} aria-label="Desfazer">
            <Undo2 size={17} />
          </button>
          <button type="button" onClick={redo} disabled={!future.length} aria-label="Refazer">
            <Redo2 size={17} />
          </button>
          <span className="sync-state" data-state={sync}>
            {sync === "saving" ? <RefreshCw size={14} /> : <Check size={14} />}
            {sync === "synced"
              ? "Alterações salvas"
              : sync === "saving"
                ? "Salvando…"
                : sync === "error"
                  ? "Falha ao salvar"
                  : "Alterações pendentes"}
          </span>
        </div>
      </header>

      {error ? <div className="editor-error" role="alert">{error}</div> : null}

      <div className="editor-body">
        <aside className="editor-candidates">
          <span className="eyebrow">Candidato selecionado</span>
          <img src={clip.poster_url ?? ""} alt="" />
          <strong>{clip.title}</strong>
          <small>{Math.round(clip.score)} pontos · plano v{serverVersion}</small>
          <span className="status-badge" data-status={stale ? "previewing" : clip.status}>
            {stale ? "Preview desatualizado" : clip.status}
          </span>
        </aside>

        <main className="editor-stage">
          <div className={`editor-player ratio-${plan.output.aspect_ratio.replace(":", "-")}`}>
            {clip.preview_url ? (
              <video src={clip.preview_url} controls playsInline preload="metadata" />
            ) : (
              <div>Preview indisponível</div>
            )}
            <div className="safe-area" aria-hidden="true" />
            {plan.editorial.overlay_enabled && plan.editorial.overlay_text ? (
              <div className="live-overlay">{plan.editorial.overlay_text}</div>
            ) : null}
          </div>
          <p>
            O player mostra o último preview físico. Ajustes ficam marcados como
            desatualizados até a regeneração.
          </p>
        </main>

        <aside className="editor-inspector">
          <div className="editor-tabs" role="tablist">
            {TABS.map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={tab === item}
                onClick={() => setTab(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <fieldset className="editor-fields" disabled={sync === "saving"}>
            {tab === "Corte" ? (
              <>
                <label>Início (ms)<input type="number" value={plan.timeline.start_ms} onChange={(e) => change((draft) => { draft.timeline.start_ms = Number(e.target.value); })} /></label>
                <label>Fim (ms)<input type="number" value={plan.timeline.end_ms} onChange={(e) => change((draft) => { draft.timeline.end_ms = Number(e.target.value); })} /></label>
                <label>Duração<input disabled value={`${(plan.timeline.duration_ms / 1000).toFixed(2)} s`} /></label>
              </>
            ) : null}
            {tab === "Layout" ? (
              <>
                <label>Enquadramento<select value={plan.layout.mode} onChange={(e) => change((draft) => { draft.layout.mode = e.target.value as typeof draft.layout.mode; })}><option value="blur_background">Fundo desfocado</option><option value="crop_center">Crop central</option></select></label>
                <label>Foco<select value={plan.layout.crop_focus ?? "center"} onChange={(e) => change((draft) => { draft.layout.crop_focus = e.target.value as "left" | "center" | "right"; })}><option value="left">Esquerda</option><option value="center">Centro</option><option value="right">Direita</option></select></label>
                <label>Desfoque<input type="range" min="0" max="30" value={plan.layout.blur_sigma ?? 12} onChange={(e) => change((draft) => { draft.layout.blur_sigma = Number(e.target.value); })} /></label>
              </>
            ) : null}
            {tab === "Legendas" ? (
              <>
                <label className="switch-row"><input type="checkbox" checked={plan.captions.enabled} onChange={(e) => change((draft) => { draft.captions.enabled = e.target.checked; })} /> Ativar legendas</label>
                <label>Tema<select value={plan.captions.theme ?? "classic"} onChange={(e) => change((draft) => { draft.captions.theme = e.target.value as "classic" | "solid" | "highlight"; })}><option value="classic">Clássico</option><option value="solid">Branco sólido</option><option value="highlight">Palavra destacada</option></select></label>
                <label>Posição<select value={plan.captions.position ?? "bottom"} onChange={(e) => change((draft) => { draft.captions.position = e.target.value as "bottom" | "center" | "top"; })}><option value="bottom">Inferior</option><option value="center">Centro</option><option value="top">Superior</option></select></label>
                <p className="field-note">O estilo é salvo no plano. A queima exige um asset de legenda, ainda não produzido pela análise atual.</p>
              </>
            ) : null}
            {tab === "Áudio" ? (
              <>
                <label className="switch-row"><input type="checkbox" checked={plan.audio.include_source} onChange={(e) => change((draft) => { draft.audio.include_source = e.target.checked; })} /> Manter áudio original</label>
                <label className="switch-row"><input type="checkbox" checked={plan.audio.normalize ?? true} onChange={(e) => change((draft) => { draft.audio.normalize = e.target.checked; })} /> Normalização EBU R128</label>
                <label>Narração<select value="none" disabled><option value="none">Sem narração</option></select></label>
                <p className="field-note">Narração externa exige upload físico de áudio; o painel não cria metadados falsos.</p>
              </>
            ) : null}
            {tab === "Editorial" ? (
              <>
                <label className="switch-row"><input type="checkbox" checked={plan.editorial.overlay_enabled ?? false} onChange={(e) => change((draft) => { draft.editorial.overlay_enabled = e.target.checked; })} /> Overlay analítico</label>
                <label>Texto<textarea maxLength={100} value={plan.editorial.overlay_text ?? ""} onChange={(e) => change((draft) => { draft.editorial.overlay_text = e.target.value; })} /></label>
                <label>Template<select value={plan.editorial.template_variant ?? "variant_default"} onChange={(e) => change((draft) => { draft.editorial.template_variant = e.target.value as "variant_default" | "variant_news" | "variant_impact"; })}><option value="variant_default">Minimalista</option><option value="variant_news">Notícias</option><option value="variant_impact">Impacto</option></select></label>
              </>
            ) : null}
            {tab === "Saída" ? (
              <>
                <label>Resolução<select value={plan.output.resolution ?? "1080x1920"} onChange={(e) => change((draft) => { draft.output.resolution = e.target.value as typeof draft.output.resolution; })}><option value="720x1280">720 × 1280</option><option value="1080x1920">1080 × 1920</option></select></label>
                <button className="editor-action" type="button" onClick={regenerate} disabled={sync !== "synced" || action !== undefined}><RefreshCw size={16} /> {action === "preview" ? "Agendando…" : "Regenerar preview"}</button>
                <button className="editor-action primary-button" type="button" onClick={render} disabled={stale || action !== undefined}><Film size={16} /> {action === "render" ? "Agendando…" : "Render final"}</button>
              </>
            ) : null}
          </fieldset>
        </aside>
      </div>

      <footer className="editor-timeline">
        {clip.preview_url ? (
          <WaveformEditor
            url={clip.preview_url}
            startMs={plan.timeline.start_ms}
            endMs={plan.timeline.end_ms}
            onBounds={(start, end) =>
              change((draft) => {
                draft.timeline.start_ms = start;
                draft.timeline.end_ms = end;
              })
            }
          />
        ) : (
          <p>Gere um preview para carregar a forma de onda.</p>
        )}
      </footer>
    </div>
  );
}
