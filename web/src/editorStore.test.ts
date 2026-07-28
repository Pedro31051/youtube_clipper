import { beforeEach, describe, expect, it } from "vitest";

import type { EditPlan } from "./api/client";
import { useEditorStore, validateTimeline } from "./editorStore";

const plan: EditPlan = {
  schema_version: "1.0.0",
  plan_version: 1,
  clip_id: "clp_test",
  source_id: "src_test",
  timeline: { start_ms: 0, end_ms: 3000, duration_ms: 3000 },
  layout: { mode: "blur_background" },
  captions: { enabled: false },
  audio: { include_source: true, normalize: true },
  editorial: { overlay_enabled: false, overlay_text: null },
  output: { aspect_ratio: "9:16", resolution: "1080x1920" }
};

beforeEach(() => {
  useEditorStore.getState().initialize("clp_test", plan);
});

describe("editor history", () => {
  it("isolates changes and restores undo/redo snapshots", () => {
    useEditorStore.getState().change((draft) => {
      draft.layout.mode = "crop_center";
    });
    expect(useEditorStore.getState().plan?.layout.mode).toBe("crop_center");
    expect(useEditorStore.getState().sync).toBe("dirty");

    useEditorStore.getState().undo();
    expect(useEditorStore.getState().plan?.layout.mode).toBe("blur_background");

    useEditorStore.getState().redo();
    expect(useEditorStore.getState().plan?.layout.mode).toBe("crop_center");
  });

  it("clears history when another clip opens", () => {
    useEditorStore.getState().change((draft) => {
      draft.timeline.end_ms = 2500;
    });
    useEditorStore.getState().initialize("clp_other", {
      ...plan,
      clip_id: "clp_other"
    });
    expect(useEditorStore.getState().past).toHaveLength(0);
    expect(useEditorStore.getState().future).toHaveLength(0);
  });
});

describe("editor validation and request identity", () => {
  it("rejects inverted, overlong and known out-of-bounds intervals", () => {
    expect(
      validateTimeline({
        ...plan,
        timeline: { start_ms: 3000, end_ms: 3000, duration_ms: 0 }
      })
    ).toBe("O fim precisa ser posterior ao início.");
    expect(
      validateTimeline({
        ...plan,
        timeline: { start_ms: 0, end_ms: 60_000, duration_ms: 60_000 }
      })
    ).toBe("O corte pode ter no máximo 59,9 segundos.");
    expect(
      validateTimeline(
        {
          ...plan,
          timeline: { start_ms: 1000, end_ms: 4000, duration_ms: 3000 }
        },
        { maxMs: 3500 }
      )
    ).toContain("não pode ultrapassar");
  });

  it("ignores a late save response after another clip is initialized", () => {
    useEditorStore.getState().change((draft) => {
      draft.timeline.end_ms = 2500;
    });
    const requestId = useEditorStore.getState().beginSave("clp_test");
    expect(requestId).toBeTypeOf("number");

    const otherPlan = { ...plan, clip_id: "clp_other" };
    useEditorStore.getState().initialize("clp_other", otherPlan);
    const accepted = useEditorStore.getState().saved(
      "clp_test",
      requestId!,
      plan,
      2
    );

    expect(accepted).toBe(false);
    expect(useEditorStore.getState().clipId).toBe("clp_other");
    expect(useEditorStore.getState().plan?.clip_id).toBe("clp_other");
  });
});
