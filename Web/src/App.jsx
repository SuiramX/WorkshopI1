import { useState, useEffect } from "react";
import "./App.css";
import SensorCard from "./components/SensorCard";
import AlertLog from "./components/AlertLog";
import HistoryChart from "./components/HistoryChart";
import WebcamFeed from "./components/WebcamFeed";
import TopbarHud from "./components/TopbarHud";

const API_STATUS_URL = import.meta.env.VITE_API_STATUS_URL || "https://192.168.1.9:8080/status";

// Structure initiale des données capteurs
const initialData = {
  temperature: 25.0,
  humidite: 50.0,
  gaz: 120.0,
  fumee: 35.0,
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

  if (Array.isArray(payload)) {
    for (const item of payload) {
      if (!item || typeof item !== "object") continue;

      if (item.temperature_level !== undefined && item.temperature_level !== null) {
        temperature = Number(item.temperature_level);
      } else if (item.temperature !== undefined && item.temperature !== null) {
        temperature = Number(item.temperature);
      } else if (item.temp !== undefined && item.temp !== null) {
        temperature = Number(item.temp);
      }

      if (item.humidity_level !== undefined && item.humidity_level !== null) {
        humidity = Number(item.humidity_level);
      } else if (item.humidity !== undefined && item.humidity !== null) {
        humidity = Number(item.humidity);
      } else if (item.humidite !== undefined && item.humidite !== null) {
        humidity = Number(item.humidite);
      }

      if (item.gas_level !== undefined && item.gas_level !== null) {
        gas = Number(item.gas_level);
      } else if (item.gas !== undefined && item.gas !== null) {
        gas = Number(item.gas);
      } else if (item.gaz !== undefined && item.gaz !== null) {
        gas = Number(item.gaz);
      }

      if (item.smoke_level !== undefined && item.smoke_level !== null) {
        smoke = Number(item.smoke_level);
      } else if (item.fumee !== undefined && item.fumee !== null) {
        smoke = Number(item.fumee);
      } else if (item.smoke !== undefined && item.smoke !== null) {
        smoke = Number(item.smoke);
      }

      if (item.presence !== undefined && item.presence !== null) {
        intrusion = Boolean(item.presence);
      } else if (item.mouvement !== undefined && item.mouvement !== null) {
        intrusion = Boolean(item.mouvement);
      } else if (item.intrusion !== undefined && item.intrusion !== null) {
        intrusion = Boolean(item.intrusion);
      }

      if (item.cyber !== undefined && item.cyber !== null) {
        cyber = Number(item.cyber);
      }
    }
  } else if (payload && typeof payload === "object") {
    if (payload.temperature_level !== undefined && payload.temperature_level !== null) {
      temperature = Number(payload.temperature_level);
    } else if (payload.temperature !== undefined && payload.temperature !== null) {
      temperature = Number(payload.temperature);
    } else if (payload.temp !== undefined && payload.temp !== null) {
      temperature = Number(payload.temp);
    }

    if (payload.humidity_level !== undefined && payload.humidity_level !== null) {
      humidity = Number(payload.humidity_level);
    } else if (payload.humidity !== undefined && payload.humidity !== null) {
      humidity = Number(payload.humidity);
    } else if (payload.humidite !== undefined && payload.humidite !== null) {
      humidity = Number(payload.humidite);
    }

    if (payload.gas_level !== undefined && payload.gas_level !== null) {
      gas = Number(payload.gas_level);
    } else if (payload.gas !== undefined && payload.gas !== null) {
      gas = Number(payload.gas);
    } else if (payload.gaz !== undefined && payload.gaz !== null) {
      gas = Number(payload.gaz);
    }

    if (payload.smoke_level !== undefined && payload.smoke_level !== null) {
      smoke = Number(payload.smoke_level);
    } else if (payload.fumee !== undefined && payload.fumee !== null) {
      smoke = Number(payload.fumee);
    } else if (payload.smoke !== undefined && payload.smoke !== null) {
      smoke = Number(payload.smoke);
    }

    if (payload.presence !== undefined && payload.presence !== null) {
      intrusion = Boolean(payload.presence);
    } else if (payload.mouvement !== undefined && payload.mouvement !== null) {
      intrusion = Boolean(payload.mouvement);
    } else if (payload.intrusion !== undefined && payload.intrusion !== null) {
      intrusion = Boolean(payload.intrusion);
    }

    if (payload.cyber !== undefined && payload.cyber !== null) {
      cyber = Number(payload.cyber);
    }
  }

  return { temperature, humidity, gas, smoke, intrusion, cyber };
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

  // Récupération des données réelles depuis l'API Rust (toutes les 10 secondes)
  useEffect(() => {
    let isMounted = true;

    const fetchSensorData = async () => {
      try {
        const response = await fetch(API_STATUS_URL, {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        });

        if (!response.ok) {
          throw new Error(`Statut HTTP: ${response.status}`);
        }

        const json = await response.json();
        if (!isMounted) return;

        const parsed = parseStatus(json);
        const currentTime = new Date().toLocaleTimeString("fr-FR");

        setData((prev) => {
          const nextTemp = parsed.temperature !== null ? parsed.temperature : prev.temperature;
          const nextHum = parsed.humidity !== null ? parsed.humidity : prev.humidite;
          const nextGas = parsed.gas !== null ? parsed.gas : prev.gaz;
          const nextSmoke = parsed.smoke !== null ? parsed.smoke : (parsed.gas !== null ? Math.round(parsed.gas * 0.3) : prev.fumee);
          const nextIntrusion = parsed.intrusion !== null ? parsed.intrusion : prev.intrusion;
          const nextCyber = parsed.cyber !== null ? parsed.cyber : prev.cyber;

          const nextData = {
            temperature: nextTemp,
            humidite: nextHum,
            gaz: nextGas,
            fumee: nextSmoke,
            intrusion: nextIntrusion,
            cyber: nextCyber,
          };

          // Mise à jour de l'historique (conservation des 30 dernières mesures)
          setHistory((prevHist) =>
            [
              ...prevHist,
              {
                time: currentTime,
                temperature: nextTemp !== null ? +Number(nextTemp).toFixed(1) : 0,
                humidite: nextHum !== null ? +Number(nextHum).toFixed(1) : 0,
                gaz: nextGas !== null ? Math.round(nextGas) : 0,
                fumee: nextSmoke !== null ? Math.round(nextSmoke) : 0,
              },
            ].slice(-30)
          );

          // Détection des alertes basées sur les données réelles
          const found = [];
          if (nextTemp !== null && nextTemp > 35) {
            found.push({ level: "critique", message: `Surchauffe thermique (${Number(nextTemp).toFixed(1)}°C)` });
          }
          if (nextGas !== null && nextGas > 400) {
            found.push({ level: "critique", message: `Fuite de gaz combustible (${Math.round(nextGas)} ppm)` });
          }
          if (nextSmoke !== null && nextSmoke > 200) {
            found.push({ level: "critique", message: `Fumées denses détectées (${Math.round(nextSmoke)} ppm)` });
          }
          if (nextHum !== null && nextHum > 80) {
            found.push({ level: "alerte", message: `Humidité excessive (${Number(nextHum).toFixed(1)}%)` });
          }
          if (nextIntrusion) {
            found.push({ level: "alerte", message: "Intrusion physique détectée (capteur PIR)" });
          }
          if (nextCyber !== null && nextCyber > 5) {
            found.push({ level: "alerte", message: "Tentatives de connexion suspectes" });
          }

          if (found.length > 0) {
            const withInfo = found.map((a) => ({ ...a, time: currentTime, id: crypto.randomUUID() }));
            setAlerts((prevAlerts) => [...withInfo, ...prevAlerts].slice(0, 20));
          }

          return nextData;
        });

        setApiStatus("connected");
      } catch (err) {
        console.warn("Erreur de communication avec l'API Rust Sentinel (/status):", err.message);
        if (isMounted) {
          setApiStatus("error");
        }
      }
    };

    // Premier appel au chargement
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
          <p className="eyebrow" style={{ marginTop: "0.25rem", fontSize: "0.7rem" }}>
            API RUST : {apiStatus === "connected" ? "EN LIGNE (10s)" : apiStatus === "error" ? "CONNEXION PERDUE" : "SYNCHRONISATION..."}
          </p>
        </div>
      </header>

      <section className="grid">
        <SensorCard
          code="DHT11"
          name="Température"
          value={data.temperature !== null ? Number(data.temperature).toFixed(1) : "--"}
          unit="°C"
          alert={data.temperature !== null && data.temperature > 35}
        />
        <SensorCard
          code="DHT11"
          name="Humidité"
          value={data.humidite !== null ? Number(data.humidite).toFixed(1) : "--"}
          unit="%"
          alert={data.humidite !== null && data.humidite > 80}
        />
        <SensorCard
          code="MQ-2"
          name="Gaz combustible"
          value={data.gaz !== null ? Math.round(data.gaz) : "--"}
          unit="ppm"
          alert={data.gaz !== null && data.gaz > 400}
        />
        <SensorCard
          code="MQ-2"
          name="Fumées"
          value={data.fumee !== null ? Math.round(data.fumee) : "--"}
          unit="ppm"
          alert={data.fumee !== null && data.fumee > 200}
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