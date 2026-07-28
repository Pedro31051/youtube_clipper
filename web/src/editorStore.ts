import { create } from "zustand";

import type { EditPlan } from "./api/client";

type SyncState = "synced" | "dirty" | "saving" | "error";

type EditorState = {
  clipId?: string;
  plan?: EditPlan;
  serverVersion: number;
  past: EditPlan[];
  future: EditPlan[];
  sync: SyncState;
  error?: string;
  initialize: (clipId: string, plan: EditPlan) => void;
  change: (mutate: (plan: EditPlan) => void) => void;
  undo: () => void;
  redo: () => void;
  saving: () => void;
  saved: (plan: EditPlan, version: number) => void;
  failed: (message: string) => void;
};

const clone = (plan: EditPlan): EditPlan => structuredClone(plan);

export const useEditorStore = create<EditorState>((set) => ({
  serverVersion: 1,
  past: [],
  future: [],
  sync: "synced",
  initialize: (clipId, plan) =>
    set({
      clipId,
      plan: clone(plan),
      serverVersion: plan.plan_version,
      past: [],
      future: [],
      sync: "synced",
      error: undefined
    }),
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
        error: undefined
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
        sync: "dirty"
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
        sync: "dirty"
      };
    }),
  saving: () => set({ sync: "saving", error: undefined }),
  saved: (plan, version) =>
    set({
      plan: clone(plan),
      serverVersion: version,
      sync: "synced",
      error: undefined
    }),
  failed: (message) => set({ sync: "error", error: message })
}));
