import { create } from "zustand";

import type { EditPlan } from "./api/client";

type SyncState = "synced" | "dirty" | "saving" | "error";

export const MAX_CLIP_DURATION_MS = 59_900;

export type TimelineBounds = {
  minMs?: number;
  maxMs?: number;
};

export function validateTimeline(
  plan: EditPlan,
  bounds: TimelineBounds = {}
): string | undefined {
  const { start_ms: startMs, end_ms: endMs } = plan.timeline;
  const minMs = bounds.minMs ?? 0;

  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) {
    return "Informe início e fim válidos.";
  }
  if (endMs <= startMs) {
    return "O fim precisa ser posterior ao início.";
  }
  if (endMs - startMs > MAX_CLIP_DURATION_MS) {
    return "O corte pode ter no máximo 59,9 segundos.";
  }
  if (startMs < minMs) {
    return `O início não pode ser anterior a ${(minMs / 1000).toFixed(3)} s.`;
  }
  if (bounds.maxMs !== undefined && endMs > bounds.maxMs) {
    return `O fim não pode ultrapassar ${(bounds.maxMs / 1000).toFixed(3)} s.`;
  }
  return undefined;
}

type EditorState = {
  clipId?: string;
  plan?: EditPlan;
  serverVersion: number;
  past: EditPlan[];
  future: EditPlan[];
  sync: SyncState;
  error?: string;
  revision: number;
  requestId: number;
  initialize: (clipId: string, plan: EditPlan) => void;
  dispose: (clipId: string) => void;
  change: (mutate: (plan: EditPlan) => void) => void;
  undo: () => void;
  redo: () => void;
  beginSave: (clipId: string) => number | undefined;
  saved: (
    clipId: string,
    requestId: number,
    plan: EditPlan,
    version: number
  ) => boolean;
  failed: (clipId: string, requestId: number, message: string) => boolean;
  retry: (clipId: string, serverVersion?: number) => void;
};

const clone = (plan: EditPlan): EditPlan => structuredClone(plan);

export const useEditorStore = create<EditorState>((set) => ({
  serverVersion: 1,
  past: [],
  future: [],
  sync: "synced",
  revision: 0,
  requestId: 0,
  initialize: (clipId, plan) =>
    set((state) => ({
      clipId,
      plan: clone(plan),
      serverVersion: plan.plan_version,
      past: [],
      future: [],
      sync: "synced",
      error: undefined,
      revision: state.revision + 1,
      requestId: state.requestId + 1
    })),
  dispose: (clipId) =>
    set((state) =>
      state.clipId === clipId
        ? {
            clipId: undefined,
            plan: undefined,
            past: [],
            future: [],
            sync: "synced",
            error: undefined,
            revision: state.revision + 1,
            requestId: state.requestId + 1
          }
        : state
    ),
  change: (mutate) =>
    set((state) => {
      if (!state.plan || state.sync === "saving") return state;
      const next = clone(state.plan);
      mutate(next);
      next.timeline.duration_ms =
        next.timeline.end_ms - next.timeline.start_ms;
      return {
        plan: next,
        past: [...state.past.slice(-29), clone(state.plan)],
        future: [],
        sync: "dirty",
        error: undefined,
        revision: state.revision + 1
      };
    }),
  undo: () =>
    set((state) => {
      const previous = state.past.at(-1);
      if (!previous || !state.plan) return state;
      return {
        plan: clone(previous),
        past: state.past.slice(0, -1),
        future: [clone(state.plan), ...state.future.slice(0, 29)],
        sync: "dirty",
        error: undefined,
        revision: state.revision + 1
      };
    }),
  redo: () =>
    set((state) => {
      const next = state.future[0];
      if (!next || !state.plan) return state;
      return {
        plan: clone(next),
        past: [...state.past.slice(-29), clone(state.plan)],
        future: state.future.slice(1),
        sync: "dirty",
        error: undefined,
        revision: state.revision + 1
      };
    }),
  beginSave: (clipId) => {
    let nextRequestId: number | undefined;
    set((state) => {
      if (
        state.clipId !== clipId ||
        !state.plan ||
        state.sync !== "dirty"
      ) {
        return state;
      }
      const requestId = state.requestId + 1;
      nextRequestId = requestId;
      return {
        sync: "saving",
        error: undefined,
        requestId
      };
    });
    return nextRequestId;
  },
  saved: (clipId, requestId, plan, version) => {
    let accepted = false;
    set((state) => {
      if (state.clipId !== clipId || state.requestId !== requestId) {
        return state;
      }
      accepted = true;
      return {
        plan: clone(plan),
        serverVersion: version,
        sync: "synced",
        error: undefined
      };
    });
    return accepted;
  },
  failed: (clipId, requestId, message) => {
    let accepted = false;
    set((state) => {
      if (state.clipId !== clipId || state.requestId !== requestId) {
        return state;
      }
      accepted = true;
      return { sync: "error", error: message };
    });
    return accepted;
  },
  retry: (clipId, serverVersion) =>
    set((state) => {
      if (state.clipId !== clipId || !state.plan) return state;
      return {
        serverVersion: serverVersion ?? state.serverVersion,
        sync: "dirty",
        error: undefined,
        revision: state.revision + 1,
        requestId: state.requestId + 1
      };
    })
}));
