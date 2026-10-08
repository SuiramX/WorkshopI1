import { useEffect, useRef, useState } from "react";

export default function WebcamFeed() {
  const canvasRef = useRef(null);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(false);
  const [measuredFps, setMeasuredFps] = useState(0);

  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;
    let isMounted = true;
    let animId = null;
    let latestBitmap = null;
    let frameCount = 0;
    let lastFpsCalc = performance.now();

    const canvas = canvasRef.current;
    const ctx = canvas ? canvas.getContext("2d") : null;

    function renderLoop() {
      if (latestBitmap && ctx && canvas) {
        if (canvas.width !== latestBitmap.width || canvas.height !== latestBitmap.height) {
          canvas.width = latestBitmap.width;
          canvas.height = latestBitmap.height;
        }
        ctx.drawImage(latestBitmap, 0, 0);
        latestBitmap.close();
        latestBitmap = null;
      }
      if (isMounted) {
        animId = requestAnimationFrame(renderLoop);
      }
    }
    animId = requestAnimationFrame(renderLoop);

    function connect() {
      if (!isMounted) return;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const defaultWsUrl = `${protocol}//${window.location.host}/ws/video`;
      const wsUrl = import.meta.env.VITE_WS_VIDEO_URL || defaultWsUrl;

      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        if (!isMounted) return;
        setActive(true);
        setError(null);
      };

      ws.onmessage = async (e) => {
        if (!isMounted) return;
        try {
          const blob = new Blob([e.data], { type: "image/jpeg" });
          const bitmap = await createImageBitmap(blob);
          if (latestBitmap) {
            latestBitmap.close();
          }
          latestBitmap = bitmap;

          frameCount++;
          const now = performance.now();
          if (now - lastFpsCalc >= 1000) {
            setMeasuredFps(Math.round((frameCount * 1000) / (now - lastFpsCalc)));
            frameCount = 0;
            lastFpsCalc = now;
          }
        } catch (err) {
          console.error("Frame render error:", err);
        }
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
        reconnectTimer = setTimeout(connect, 2000);
      };
    }

    connect();

    return () => {
      isMounted = false;
      if (animId) cancelAnimationFrame(animId);
      if (latestBitmap) latestBitmap.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
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
            <canvas ref={canvasRef} className="webcam-video" />
            <div className="webcam-overlay">
              <span className="webcam-tag">
                <i className="dot" style={{ background: active ? "var(--red)" : "var(--muted)" }}></i>
                {active ? "REC // LIVE" : "CONNEXION..."}
              </span>
              <span className="webcam-fps">{active && measuredFps > 0 ? `${measuredFps} FPS` : "LIVE STREAM"} // HD</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}