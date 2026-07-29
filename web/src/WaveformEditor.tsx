import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, {
  type Region
} from "wavesurfer.js/dist/plugins/regions.esm.js";

const MIN_REGION_SECONDS = 0.1;
const MAX_REGION_SECONDS = 59.9;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function WaveformEditor({
  url,
  startMs,
  endMs,
  mediaStartMs = 0,
  mediaEndMs,
  disabled = false,
  onBounds
}: {
  url: string;
  startMs: number;
  endMs: number;
  mediaStartMs?: number;
  mediaEndMs?: number;
  disabled?: boolean;
  onBounds: (startMs: number, endMs: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const regionRef = useRef<Region | undefined>(undefined);
  const durationMsRef = useRef(0);
  const callbackRef = useRef(onBounds);
  const startRef = useRef(startMs);
  const endRef = useRef(endMs);
  const mediaStartRef = useRef(mediaStartMs);
  const mediaEndRef = useRef(mediaEndMs);
  const disabledRef = useRef(disabled);

  callbackRef.current = onBounds;
  startRef.current = startMs;
  endRef.current = endMs;
  mediaStartRef.current = mediaStartMs;
  mediaEndRef.current = mediaEndMs;
  disabledRef.current = disabled;

  function updateRegion() {
    const region = regionRef.current;
    const durationMs = durationMsRef.current;
    if (!region || durationMs <= 0) return;

    const baseMs = mediaStartRef.current;
    const availableEndMs = Math.min(
      baseMs + durationMs,
      mediaEndRef.current ?? Number.POSITIVE_INFINITY
    );
    const nextStartMs = clamp(startRef.current, baseMs, availableEndMs);
    const nextEndMs = clamp(endRef.current, nextStartMs, availableEndMs);
    region.setOptions({
      start: (nextStartMs - baseMs) / 1000,
      end: (nextEndMs - baseMs) / 1000,
      resize: !disabledRef.current,
      resizeStart: !disabledRef.current,
      resizeEnd: !disabledRef.current
    });
  }

  useEffect(() => {
    if (!container.current) return;
    const regions = RegionsPlugin.create();
    const wavesurfer = WaveSurfer.create({
      container: container.current,
      url,
      mediaControls: false,
      height: 74,
      waveColor: "#536176",
      progressColor: "#6d95ff",
      cursorColor: "#f5f7fa",
      normalize: true,
      plugins: [regions]
    });

    wavesurfer.on("ready", (durationSeconds) => {
      durationMsRef.current = Math.max(0, Math.round(durationSeconds * 1000));
      const baseMs = mediaStartRef.current;
      const availableEndMs = Math.min(
        baseMs + durationMsRef.current,
        mediaEndRef.current ?? Number.POSITIVE_INFINITY
      );
      const initialStartMs = clamp(startRef.current, baseMs, availableEndMs);
      const initialEndMs = clamp(endRef.current, initialStartMs, availableEndMs);
      regionRef.current = regions.addRegion({
        id: "active-cut",
        start: (initialStartMs - baseMs) / 1000,
        end: (initialEndMs - baseMs) / 1000,
        color: "rgba(109,149,255,.18)",
        drag: false,
        resize: !disabledRef.current,
        resizeStart: !disabledRef.current,
        resizeEnd: !disabledRef.current,
        minLength: Math.min(MIN_REGION_SECONDS, durationSeconds),
        maxLength: Math.min(MAX_REGION_SECONDS, durationSeconds)
      });
    });

    regions.on("region-updated", (region) => {
      if (disabledRef.current) return;
      const baseMs = mediaStartRef.current;
      const availableEndMs = Math.min(
        baseMs + durationMsRef.current,
        mediaEndRef.current ?? Number.POSITIVE_INFINITY
      );
      const nextStartMs = clamp(
        Math.round(baseMs + region.start * 1000),
        baseMs,
        availableEndMs
      );
      const nextEndMs = clamp(
        Math.round(baseMs + region.end * 1000),
        nextStartMs,
        availableEndMs
      );
      callbackRef.current(nextStartMs, nextEndMs);
    });

    return () => {
      regionRef.current = undefined;
      durationMsRef.current = 0;
      wavesurfer.destroy();
    };
  }, [url]);

  useEffect(() => {
    updateRegion();
  }, [startMs, endMs, mediaStartMs, mediaEndMs, disabled]);

  return (
    <div
      className="waveform-shell"
      role="group"
      aria-label="Intervalo na forma de onda do preview"
      aria-disabled={disabled || undefined}
    >
      <div
        ref={container}
        className="waveform-canvas"
        aria-label="Forma de onda do preview"
      />
      <div className="waveform-scale" aria-hidden="true">
        <span>{(mediaStartMs / 1000).toFixed(1)} s</span>
        <span>
          {disabled ? "salvando intervalo" : "arraste os limites do intervalo"}
        </span>
        <span>
          {((mediaEndMs ?? mediaStartMs + durationMsRef.current) / 1000).toFixed(1)} s
        </span>
      </div>
    </div>
  );
}
