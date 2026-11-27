import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { OwnerAccess } from "./OwnerAccess";
import "./style.css";

type DemoData = { demo: true; items: string[] };

function isDemoData(value: unknown): value is DemoData {
  if (typeof value !== "object" || value === null || !("demo" in value) || !("items" in value)) {
    return false;
  }
  return value.demo === true && Array.isArray(value.items) && value.items.every((item) => typeof item === "string");
}

function App() {
  const [demo, setDemo] = useState<DemoData | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/demo", { signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((value: unknown) => {
        if (isDemoData(value)) setDemo(value);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  return (
    <main>
      <p className="brand">PersonalContext</p>
      {demo && <p className="demo-label">DEMO · Синтетические данные</p>}
      <h1>Ваш контекст начинается здесь</h1>
      <p>Источники пока не подключены. Сбор активности выключен.</p>
      <OwnerAccess />
      {demo && (
        <section>
          <h2>Примеры материалов</h2>
          <ul>{demo.items.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
