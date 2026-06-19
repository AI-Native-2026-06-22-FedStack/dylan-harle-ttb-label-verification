import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function fetchHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`);

        if (!response.ok) {
          throw new Error(`Health check failed with status ${response.status}`);
        }

        const data = await response.json();

        if (isMounted) {
          setHealth(data);
          setError("");
        }
      } catch (fetchError) {
        if (isMounted) {
          setHealth(null);
          setError(fetchError instanceof Error ? fetchError.message : "Health check failed");
        }
      }
    }

    fetchHealth();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="page-shell">
      <section className="status-panel" aria-live="polite">
        <p className="eyebrow">TTB Label Verification</p>
        <h1>Deployment Check</h1>

        {health ? (
          <div className="result result-ok">
            <strong>Connected</strong>
            <pre>{JSON.stringify(health, null, 2)}</pre>
          </div>
        ) : (
          <div className="result result-error">
            <strong>{error ? "Not connected" : "Checking connection"}</strong>
            <p>{error || "Contacting the backend health endpoint..."}</p>
          </div>
        )}
      </section>
    </main>
  );
}

export default App;

