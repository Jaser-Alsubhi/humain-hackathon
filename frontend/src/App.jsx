import { useEffect, useState } from "react";

export default function App() {
  const [health, setHealth] = useState("loading...");
  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then((r) => r.json())
      .then((d) => setHealth(JSON.stringify(d)))
      .catch(() => setHealth("backend unreachable"));
  }, []);
  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>HUMAIN Hack</h1>
      <p>Backend: {health}</p>
    </main>
  );
}
