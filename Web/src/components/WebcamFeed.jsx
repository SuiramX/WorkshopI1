import { useEffect, useRef, useState } from "react";

export default function WebcamFeed() {
  const imgRef = useRef(null);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    let lastUrl = null;
    let ws = null;
    let reconnectTimer = null;
    let isMounted = true;

    function connect() {
      if (!isMounted) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      // window.location.host includes hostname and port (e.g. 192.168.1.9:3000)
      const defaultWsUrl = `${protocol}//${window.location.host}/ws/video`;
      const wsUrl = import.meta.env.VITE_WS_VIDEO_URL || defaultWsUrl;

      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        if (!isMounted) return;
        setActive(true);
        setError(null);
      };

      ws.onmessage = (e) => {
        if (!isMounted) return;
        const blob = new Blob([e.data], { type: "image/jpeg" });
        const url = URL.createObjectURL(blob);
        if (imgRef.current) {
          imgRef.current.src = url;
        }
        if (lastUrl) {
          URL.revokeObjectURL(lastUrl);
        }
        lastUrl = url;
      };

      ws.onerror = (err) => {
        console.error("Erreur WebSocket webcam:", err);
        if (!isMounted) return;
        setError("FLUX CAMÉRA NON DISPONIBLE OU ERREUR DE CONNEXION");
        setActive(false);
      };

      ws.onclose = () => {
        if (!isMounted) return;
        setActive(false);
        // Automatic reconnection attempt after 2.5 seconds
        reconnectTimer = setTimeout(connect, 2500);
      };
    }

    connect();

    return () => {
      isMounted = false;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (ws) {
        ws.close();
      }
      if (lastUrl) {
        URL.revokeObjectURL(lastUrl);
      }
    };
  }, []);

  return (
    <section className="chart-panel webcam-panel">
      <h2>FLUX VIDÉO EN DIRECT // CAM-01</h2>
      <div className="webcam-container">
        {error ? (
          <div className="webcam-error">
            <span className="card-state" style={{ color: "var(--red)" }}>
              ⚠ {error}
            </span>
          </div>
        ) : (
          <>
            <img id="video" ref={imgRef} alt="Flux vidéo live" className="webcam-video" />
            <div className="webcam-overlay">
              <span className="webcam-tag">
                <i className="dot" style={{ background: active ? "var(--red)" : "var(--muted)" }}></i>
                {active ? "REC // LIVE" : "CONNEXION..."}
              </span>
              <span className="webcam-fps">30 FPS // 1080P</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}