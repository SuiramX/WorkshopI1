import { useEffect, useRef, useState } from "react";

export default function WebcamFeed() {
  const imgRef = useRef(null);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    let lastUrl = null;
    const ws = new WebSocket("ws://192.168.1.9:8080/video");
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setActive(true);
      setError(null);
    };

    ws.onmessage = (e) => {
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
      setError("FLUX CAMÉRA NON DISPONIBLE OU ERREUR DE CONNEXION");
      setActive(false);
    };

    ws.onclose = () => {
      setActive(false);
    };

    return () => {
      ws.close();
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