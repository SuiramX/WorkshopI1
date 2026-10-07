import { useState, useEffect, useRef } from "react";
import "./App.css";
import SensorCard from "./components/SensorCard";
import AlertLog from "./components/AlertLog";
import HistoryChart from "./components/HistoryChart";
import WebcamFeed from "./components/WebcamFeed";
import TopbarHud from "./components/TopbarHud";

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
const drift = (v, amp) => v + (Math.random() - 0.5) * amp;

// Calcule la mesure suivante à partir de la précédente (simulation)
function nextMeasure(prev) {
  return {
    temperature: clamp(drift(prev.temperature, 4), 18, 42),
    humidite: clamp(drift(prev.humidite, 6), 30, 90),
    gaz: clamp(drift(prev.gaz, 120), 0, 600),
    fumee: clamp(drift(prev.fumee, 60), 0, 300),
    intrusion: Math.random() < 0.08,
    cyber: Math.floor(Math.random() * 8),
  };
}

const initial = {
  temperature: 25,
  humidite: 55,
  gaz: 150,
  fumee: 40,
  intrusion: false,
  cyber: 0,
};

export default function App() {
  const [data, setData] = useState(initial);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [time, setTime] = useState(new Date().toLocaleTimeString("fr-FR"));
  const last = useRef(initial);

  // Horloge en temps réel (mise à jour chaque seconde)
  useEffect(() => {
    const clockId = setInterval(() => {
      setTime(new Date().toLocaleTimeString("fr-FR"));
    }, 1000);
    return () => clearInterval(clockId);
  }, []);

  // Simulation des mesures et gestion des alertes (toutes les 2 secondes)
  useEffect(() => {
    const id = setInterval(() => {
      const next = nextMeasure(last.current);
      last.current = next;
      setData(next);

      const currentTime = new Date().toLocaleTimeString("fr-FR");

      // Historique : conservation des 30 dernières mesures
      setHistory((prev) =>
        [
          ...prev,
          {
            time: currentTime,
            temperature: +next.temperature.toFixed(1),
            humidite: +next.humidite.toFixed(1),
            gaz: Math.round(next.gaz),
            fumee: Math.round(next.fumee),
          },
        ].slice(-30)
      );

      // Détection des seuils d'alerte
      const found = [];
      if (next.temperature > 35) found.push({ level: "critique", message: "Surchauffe thermique" });
      if (next.gaz > 400) found.push({ level: "critique", message: "Fuite de gaz combustible" });
      if (next.fumee > 200) found.push({ level: "critique", message: "Fumées détectées" });
      if (next.humidite > 80) found.push({ level: "alerte", message: "Humidité excessive" });
      if (next.intrusion) found.push({ level: "alerte", message: "Intrusion physique détectée" });
      if (next.cyber > 5) found.push({ level: "alerte", message: "Tentatives de connexion suspectes" });

      if (found.length > 0) {
        const withInfo = found.map((a) => ({ ...a, time: currentTime, id: crypto.randomUUID() }));
        setAlerts((prev) => [...withInfo, ...prev].slice(0, 20));
      }
    }, 2000);

    return () => clearInterval(id);
  }, []);

  // Calcul du niveau de menace global
  const criticalCount = alerts.slice(0, 5).filter((a) => a.level === "critique").length;
  const threatLevel = criticalCount >= 2 ? "CRITIQUE" : criticalCount === 1 ? "ÉLEVÉ" : "NOMINAL";
  const threatColor =
    threatLevel === "CRITIQUE" ? "var(--red)" : threatLevel === "ÉLEVÉ" ? "var(--amber)" : "var(--green)";

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="topbar-left">
          <p className="eyebrow">AETHERCORP INDUSTRIAL SOLUTIONS</p>
          <h1>SENTINEL-X</h1>
          <p className="subtitle">Centre de commandement tactique</p>
        </div>

        {/* Habillage graphique central */}
        <TopbarHud />

        <div className="topbar-right" style={{ textAlign: "right" }}>
          <p className="eyebrow" style={{ marginBottom: "0.2rem" }}>{time}</p>
          <span className="status" style={{ color: threatColor, textShadow: `0 0 10px ${threatColor}` }}>
            <i className="dot" style={{ background: threatColor, boxShadow: `0 0 12px ${threatColor}` }}></i>
            MENACE : {threatLevel}
          </span>
        </div>
      </header>

      <section className="grid">
        <SensorCard code="DHT22" name="Température" value={data.temperature.toFixed(1)} unit="°C" alert={data.temperature > 35} />
        <SensorCard code="DHT22" name="Humidité" value={data.humidite.toFixed(1)} unit="%" alert={data.humidite > 80} />
        <SensorCard code="MQ-2" name="Gaz combustible" value={Math.round(data.gaz)} unit="ppm" alert={data.gaz > 400} />
        <SensorCard code="MQ-2" name="Fumées" value={Math.round(data.fumee)} unit="ppm" alert={data.fumee > 200} />
        <SensorCard code="HC-SR501" name="Intrusion" value={data.intrusion ? "DÉTECTÉE" : "AUCUNE"} unit="" alert={data.intrusion} />
        <SensorCard code="NX-06" name="Événements cyber" value={data.cyber} unit="/min" alert={data.cyber > 5} />
      </section>

      {/* DISPOSITION 2 COLONNES : WEBCAM (GAUCHE) / GRAPHIQUES (DROITE) */}
      <section className="main-media-grid">
        <div className="media-left">
          <WebcamFeed />
        </div>

        <div className="media-right">
          <HistoryChart
            title="Température / Humidité"
            data={history}
            lines={[
              { key: "temperature", label: "Température (°C)", color: "#ff9f1c" },
              { key: "humidite", label: "Humidité (%)", color: "#00e5ff" },
            ]}
          />
          <HistoryChart
            title="Gaz / Fumées"
            data={history}
            lines={[
              { key: "gaz", label: "Gaz (ppm)", color: "#ff2e63" },
              { key: "fumee", label: "Fumées (ppm)", color: "#a855f7" },
            ]}
          />
        </div>
      </section>

      <AlertLog alerts={alerts} />
    </div>
  );
}