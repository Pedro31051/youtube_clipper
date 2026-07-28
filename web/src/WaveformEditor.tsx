import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";

export function WaveformEditor({
  url,
  startMs,
  endMs,
  onBounds
}: {
  url: string;
  startMs: number;
  endMs: number;
  onBounds: (startMs: number, endMs: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onBounds);
  callback.current = onBounds;

  useEffect(() => {
    if (!container.current) return;
    const regions = RegionsPlugin.create();
    const wavesurfer = WaveSurfer.create({
      container: container.current,
      url,
      height: 74,
      waveColor: "#536176",
      progressColor: "#6d95ff",
      cursorColor: "#f5f7fa",
      normalize: true,
      plugins: [regions]
    });
    const baseStart = startMs;
    wavesurfer.on("ready", (duration) => {
      regions.addRegion({
        id: "active-cut",
        start: 0,
        end: Math.min(duration, (endMs - startMs) / 1000),
        color: "rgba(109,149,255,.18)",
        drag: false,
        resize: true,
        minLength: 1
      });
    });
    regions.on("region-updated", (region) => {
      callback.current(
        Math.round(baseStart + region.start * 1000),
        Math.round(baseStart + region.end * 1000)
      );
    });
    return () => wavesurfer.destroy();
  }, [url]);

  return (
    <div className="waveform-shell">
      <div ref={container} aria-label="Forma de onda do preview" />
      <div className="waveform-scale" aria-hidden="true">
        <span>{(startMs / 1000).toFixed(1)}s</span>
        <span>arraste os limites do intervalo</span>
        <span>{(endMs / 1000).toFixed(1)}s</span>
      </div>
    </div>
  );
}
