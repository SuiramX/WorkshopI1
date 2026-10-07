import { useEffect, useRef, useState } from "react";

export default function WebcamFeed() {
  const videoRef = useRef(null);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    let streamInstance = null;

    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { 
            width: { ideal: 1920 }, 
            height: { ideal: 1080 } 
          },
          audio: false,
        });
        streamInstance = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setActive(true);
        }
      } catch (err) {
        console.error("Erreur accès webcam:", err);
        setError("FLUX CAMÉRA NON DISPONIBLE OU ACCÈS REFUSÉ");
      }
    }

    startCamera();

    return () => {
      if (streamInstance) {
        streamInstance.getTracks().forEach((track) => track.stop());
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
            <video ref={videoRef} autoPlay playsInline muted className="webcam-video" />
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