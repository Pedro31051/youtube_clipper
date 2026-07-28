import { beforeEach, describe, expect, it } from "vitest";

import type { EditPlan } from "./api/client";
import { useEditorStore } from "./editorStore";

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
