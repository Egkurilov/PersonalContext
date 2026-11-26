import { createRoot } from "react-dom/client";
import "./style.css";

function App() {
  return <main><p className="brand">PersonalContext</p><h1>Ваш контекст начинается здесь</h1><p>Источники пока не подключены. Сбор активности выключен.</p></main>;
}

createRoot(document.getElementById("root")!).render(<App />);
