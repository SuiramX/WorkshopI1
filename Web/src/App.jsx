import { useState, useEffect } from "react";
import "./App.css";
import SensorCard from "./components/SensorCard";
import AlertLog from "./components/AlertLog";
import HistoryChart from "./components/HistoryChart";
import WebcamFeed from "./components/WebcamFeed";
import TopbarHud from "./components/TopbarHud";

// URL de base de l'API Rust — configurable via variable d'environnement Vite
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "https://192.168.1.9:8080").replace(/\/$/, "");

// Structure initiale des données capteurs (affiché avant le premier appel API)
const initialData = {
  temperature: null,
  humidite: null,
  gaz: null,
  fumee: null,
  intrusion: false,
  cyber: 0,
};

// Extraction et normalisation des données issues de l'API Rust /status
function parseStatus(payload) {
  let temperature = null;
  let humidity = null;
  let gas = null;
  let smoke = null;
  let intrusion = null;
  let cyber = null;

  const items = Array.isArray(payload) ? payload : [payload];

  for (const item of items) {
    if (!item || typeof item !== "object") continue;

    if (item.temperature_level != null) temperature = Number(item.temperature_level);
    else if (item.temperature != null) temperature = Number(item.temperature);
    else if (item.temp != null) temperature = Number(item.temp);

    if (item.humidity_level != null) humidity = Number(item.humidity_level);
    else if (item.humidity != null) humidity = Number(item.humidity);
    else if (item.humidite != null) humidity = Number(item.humidite);

    if (item.gas_level != null) gas = Number(item.gas_level);
    else if (item.gas != null) gas = Number(item.gas);
    else if (item.gaz != null) gas = Number(item.gaz);

    if (item.smoke_level != null) smoke = Number(item.smoke_level);
    else if (item.fumee != null) smoke = Number(item.fumee);
    else if (item.smoke != null) smoke = Number(item.smoke);

    if (item.presence != null) intrusion = Boolean(item.presence);
    else if (item.mouvement != null) intrusion = Boolean(item.mouvement);
    else if (item.intrusion != null) intrusion = Boolean(item.intrusion);

    if (item.cyber != null) cyber = Number(item.cyber);
  }

  return { temperature, humidity, gas, smoke, intrusion, cyber };
}

// Déclenche une lecture capteur sans bloquer (fire & forget avec timeout)
function triggerSensor(path) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  return fetch(`${API_BASE}${path}`, { signal: ctrl.signal })
    .catch(() => {}) // erreur ignorée volontairement
    .finally(() => clearTimeout(timer));
}

export default function App() {
  const [data, setData] = useState(initialData);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [time, setTime] = useState(new Date().toLocaleTimeString("fr-FR"));
  const [apiStatus, setApiStatus] = useState("connecting"); // 'connected' | 'error' | 'connecting'

  // Horloge en temps réel (mise à jour chaque seconde)
  useEffect(() => {
    const clockId = setInterval(() => {
      setTime(new Date().toLocaleTimeString("fr-FR"));
    }, 1000);
    return () => clearInterval(clockId);
  }, []);

  // Cycle principal : ping capteurs → attendre → récupérer /status
  useEffect(() => {
    let isMounted = true;

    const fetchSensorData = async () => {
      // ── Étape 1 : déclencher les 3 capteurs en parallèle pour peupler la BDD
      // Ces appels publient sur MQTT (esp8266/cmd) et stockent la réponse en base.
      // On les lance en parallèle et on attend qu'ils se terminent (ou timeout 8s).
      await Promise.allSettled([
        triggerSensor("/temperature/sensor"),
        triggerSensor("/humidity/sensor"),
        triggerSensor("/gas/sensor"),
      ]);

      if (!isMounted) return;

      // ── Étape 2 : lire le dernier état depuis la BDD via /status
      try {
        const response = await fetch(`${API_BASE}/status`, {
          headers: { Accept: "application/json" },
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const json = await response.json();
        if (!isMounted) return;

        const parsed = parseStatus(json);
        const currentTime = new Date().toLocaleTimeString("fr-FR");

        setData((prev) => {
          const nextTemp     = parsed.temperature !== null ? parsed.temperature : prev.temperature;
          const nextHum      = parsed.humidity    !== null ? parsed.humidity    : prev.humidite;
          const nextGas      = parsed.gas         !== null ? parsed.gas         : prev.gaz;
          const nextSmoke    = parsed.smoke       !== null ? parsed.smoke
                             : parsed.gas         !== null ? Math.round(parsed.gas * 0.3)
                             : prev.fumee;
          const nextIntrusion = parsed.intrusion !== null ? parsed.intrusion : prev.intrusion;
          const nextCyber     = parsed.cyber      !== null ? parsed.cyber     : prev.cyber;

          const nextData = {
            temperature: nextTemp,
            humidite:    nextHum,
            gaz:         nextGas,
            fumee:       nextSmoke,
            intrusion:   nextIntrusion,
            cyber:       nextCyber,
          };

          // Historique : 30 dernières mesures pour les graphiques
          setHistory((prev) =>
            [
              ...prev,
              {
                time:        currentTime,
                temperature: nextTemp  != null ? +Number(nextTemp).toFixed(1)  : null,
                humidite:    nextHum   != null ? +Number(nextHum).toFixed(1)   : null,
                gaz:         nextGas   != null ? Math.round(nextGas)           : null,
                fumee:       nextSmoke != null ? Math.round(nextSmoke)         : null,
              },
            ].slice(-30)
          );

          // Détection des seuils d'alerte
          const found = [];
          if (nextTemp  != null && nextTemp  > 35)  found.push({ level: "critique", message: `Surchauffe thermique (${Number(nextTemp).toFixed(1)}°C)` });
          if (nextGas   != null && nextGas   > 400) found.push({ level: "critique", message: `Fuite de gaz combustible (${Math.round(nextGas)} ppm)` });
          if (nextSmoke != null && nextSmoke > 200) found.push({ level: "critique", message: `Fumées denses détectées (${Math.round(nextSmoke)} ppm)` });
          if (nextHum   != null && nextHum   > 80)  found.push({ level: "alerte",   message: `Humidité excessive (${Number(nextHum).toFixed(1)}%)` });
          if (nextIntrusion)                         found.push({ level: "alerte",   message: "Intrusion physique détectée (capteur PIR)" });
          if (nextCyber != null && nextCyber > 5)   found.push({ level: "alerte",   message: "Tentatives de connexion suspectes" });

          if (found.length > 0) {
            const withInfo = found.map((a) => ({ ...a, time: currentTime, id: crypto.randomUUID() }));
            setAlerts((prev) => [...withInfo, ...prev].slice(0, 20));
          }

          return nextData;
        });

        setApiStatus("connected");
      } catch (err) {
        console.warn("[Sentinel] Erreur /status :", err.message);
        if (isMounted) setApiStatus("error");
      }
    };

    // Premier appel immédiat au chargement de la page
    fetchSensorData();

    // Répétition toutes les 10 secondes
    const intervalId = setInterval(fetchSensorData, 10000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  // Calcul du niveau de menace global
  const criticalCount = alerts.slice(0, 5).filter((a) => a.level === "critique").length;
  const threatLevel   = criticalCount >= 2 ? "CRITIQUE" : criticalCount === 1 ? "ÉLEVÉ" : "NOMINAL";
  const threatColor   = threatLevel === "CRITIQUE" ? "var(--red)" : threatLevel === "ÉLEVÉ" ? "var(--amber)" : "var(--green)";

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="topbar-left">
          <p className="eyebrow">AETHERCORP INDUSTRIAL SOLUTIONS</p>
          <h1>SENTINEL-X</h1>
          <p className="subtitle">Centre de commandement tactique</p>
        </div>

        <TopbarHud />

        <div className="topbar-right" style={{ textAlign: "right" }}>
          <p className="eyebrow" style={{ marginBottom: "0.2rem" }}>{time}</p>
          <span className="status" style={{ color: threatColor, textShadow: `0 0 10px ${threatColor}` }}>
            <i className="dot" style={{ background: threatColor, boxShadow: `0 0 12px ${threatColor}` }}></i>
            MENACE : {threatLevel}
          </span>
          <p className="eyebrow" style={{ marginTop: "0.25rem", fontSize: "0.7rem" }}>
            API :{" "}
            {apiStatus === "connected"
              ? "EN LIGNE // POLL 10s"
              : apiStatus === "error"
              ? "⚠ CONNEXION PERDUE"
              : "SYNCHRONISATION..."}
          </p>
        </div>
      </header>

      <section className="grid">
        <SensorCard
          code="DHT11"
          name="Température"
          value={data.temperature != null ? Number(data.temperature).toFixed(1) : "--"}
          unit="°C"
          alert={data.temperature != null && data.temperature > 35}
        />
        <SensorCard
          code="DHT11"
          name="Humidité"
          value={data.humidite != null ? Number(data.humidite).toFixed(1) : "--"}
          unit="%"
          alert={data.humidite != null && data.humidite > 80}
        />
        <SensorCard
          code="MQ-2"
          name="Gaz combustible"
          value={data.gaz != null ? Math.round(data.gaz) : "--"}
          unit="ppm"
          alert={data.gaz != null && data.gaz > 400}
        />
        <SensorCard
          code="MQ-2"
          name="Fumées"
          value={data.fumee != null ? Math.round(data.fumee) : "--"}
          unit="ppm"
          alert={data.fumee != null && data.fumee > 200}
        />
        <SensorCard
          code="HC-SR501"
          name="Intrusion"
          value={data.intrusion ? "DÉTECTÉE" : "AUCUNE"}
          unit=""
          alert={Boolean(data.intrusion)}
        />
        <SensorCard
          code="NX-06"
          name="Événements cyber"
          value={data.cyber ?? 0}
          unit="/min"
          alert={data.cyber > 5}
        />
      </section>

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
              { key: "humidite",    label: "Humidité (%)",      color: "#00e5ff" },
            ]}
          />
          <HistoryChart
            title="Gaz / Fumées"
            data={history}
            lines={[
              { key: "gaz",   label: "Gaz (ppm)",    color: "#ff2e63" },
              { key: "fumee", label: "Fumées (ppm)", color: "#a855f7" },
            ]}
          />
        </div>
      </section>

      <AlertLog alerts={alerts} />
    </div>
  );
}