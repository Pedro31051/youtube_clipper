import { useEffect, useState } from "react";

import type { Job } from "../api/client";

export type JobEvent = {
  seq: number;
  job_id: string;
  type: string;
  state: string;
  progress: number;
  message: string;
  timestamp_ms: number;
};

const TERMINAL_STATES = ["completed", "failed", "cancelled", "interrupted"];

export function useJobEvents(job: Job | undefined) {
  const [event, setEvent] = useState<JobEvent | null>(null);
  const [connection, setConnection] = useState<
    "idle" | "connecting" | "live" | "closed"
  >("idle");

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.state)) {
      setEvent(null);
      setConnection("idle");
      return;
    }
    setEvent(null);
    setConnection("connecting");
    const stream = new EventSource(
      `/api/v1/jobs/${encodeURIComponent(job.job_id)}/events`
    );
    const consume = (message: MessageEvent<string>) => {
      const next = JSON.parse(message.data) as JobEvent;
      setEvent(next);
      setConnection(TERMINAL_STATES.includes(next.state) ? "closed" : "live");
    };
    [
      "job_queued",
      "stage_start",
      "progress",
      "stage_completed",
      "job_failed",
      "job_cancelled",
      "job_interrupted"
    ].forEach((type) =>
      stream.addEventListener(type, consume as EventListener)
    );
    stream.onopen = () => setConnection("live");
    stream.onerror = () => setConnection("closed");
    return () => stream.close();
  }, [job?.job_id, job?.state]);

  return { event, connection };
}
