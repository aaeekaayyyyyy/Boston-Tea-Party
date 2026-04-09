import { useEffect, useState } from "react";

/**
 * Fetches GET /api/health once on mount (planning API + RAG readiness).
 */
export function useBackendHealth() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText || "health failed");
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setHealth({ ok: true, data });
      })
      .catch((e) => {
        if (!cancelled) setHealth({ ok: false, error: String(e.message || e) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return health;
}
