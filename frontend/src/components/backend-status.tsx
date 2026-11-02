"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "connected" | "unavailable";

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    async function checkHealth() {
      setStatus("checking");
      try {
        const response = await fetch("/api/v1/health", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Health request failed");
        const body: unknown = await response.json();
        if (
          typeof body !== "object" || body === null ||
          !("status" in body) || body.status !== "ok"
        ) throw new Error("Unexpected health response");
        if (active) setStatus("connected");
      } catch {
        if (active) setStatus("unavailable");
      } finally {
        clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  return (
    <section className="connection" aria-labelledby="connection-title">
      <h2 id="connection-title">Local connection</h2>
      <p role="status" className={`status ${status}`}>
        {status === "checking" && "Checking the API…"}
        {status === "connected" && "API connected"}
        {status === "unavailable" && "API unavailable. Start the backend, then try again."}
      </p>
      <button disabled={status === "checking"} onClick={() => setAttempt((value) => value + 1)}>
        Check again
      </button>
    </section>
  );
}
