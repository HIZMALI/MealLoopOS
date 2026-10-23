import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";

type Runtime = {
  mode: "LOCAL" | "PUBLIC_DEMO";
  version: string;
  read_only: boolean;
  notice: string;
};
const RuntimeContext = createContext<Runtime | null>(null);
export function useRuntime() {
  const value = useContext(RuntimeContext);
  if (!value) throw new Error("Server configuration is unavailable.");
  return value;
}
export function RuntimeGate({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Runtime | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    api<Runtime>("/config")
      .then((value) => {
        if (
          !["LOCAL", "PUBLIC_DEMO"].includes(value.mode) ||
          value.read_only !== (value.mode === "PUBLIC_DEMO")
        )
          throw new Error("Invalid server configuration.");
        if (active) setConfig(value);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  if (!config)
    return (
      <main className="release-start" aria-live="polite">
        <p className="eyebrow">MEALLOOP OS</p>
        <h1>
          {error ? "Connection needs attention" : "Opening your workspace…"}
        </h1>
        <p>
          {error ||
            "A sleeping demo host may take about a minute to wake. No data is being changed."}
        </p>
        {error && (
          <button
            className="button primary"
            onClick={() => setAttempt((a) => a + 1)}
          >
            Retry connection
          </button>
        )}
      </main>
    );
  return (
    <RuntimeContext.Provider value={config}>{children}</RuntimeContext.Provider>
  );
}
