import os
import glob
import time
import base64
import queue
import urllib.parse
import urllib.request
import threading
import asyncio
import logging
import requests
import cv2
import numpy as np
from ultralytics import YOLO

# ── CONFIGURATION ──
STREAM_SERVER_URL = os.getenv("STREAM_SERVER_URL", "http://localhost:8001")
API_FRAME_URL = f"{STREAM_SERVER_URL}/api/v1/video/frame"
CONFIDENCE_THRESHOLD = 0.50          # Seuil détection YOLOv8

# ── CONFIGURATION ──
API_ALERTS_URL = os.getenv("API_ALERTS_URL", "http://api:8080/api/v1/alerts")
STREAM_SERVER_URL = os.getenv("STREAM_SERVER_URL", "ws://video:8765/publish")
WS_AUTH_TOKEN = os.getenv("WS_AUTH_TOKEN", "sentinel_ws_secure_stream_token_9x7k2")

CAMERA_NAME = os.getenv("CAMERA_NAME", "C920")
DEVICE_CONFIG = os.getenv("DEVICE", "auto")
TARGET_FPS = int(os.getenv("FPS", "25"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "65"))

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.50"))  # Seuil détection YOLOv8
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.40"))  # Seuil cosinus SFace (>= 0.40 = même personne)
ALERT_COOLDOWN_SEC = float(os.getenv("ALERT_COOLDOWN_SEC", "5.0"))      # Pause anti-spam entre alertes
ENABLE_GUI = os.getenv("ENABLE_GUI", "false").lower() in ("true", "1", "yes")

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Classes COCO surveillées :
# Détecte les humains + véhicules + électronique + sacs / armes.
MONITORED_CLASSES = {
    "person", "laptop", "tv", "cell phone", "car", "motorcycle",
    "bus", "truck", "bicycle", "backpack", "suitcase", "knife"
}

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
FACES_DIR = os.path.join(os.path.dirname(__file__), "authorized_faces")
BLACKLIST_DIR = os.path.join(os.path.dirname(__file__), "blacklist")

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface.onnx")

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2026mar.onnx"
SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"


# ─────────────────────────────────────────────────────────────
# MODULE DE STREAMING WEBSOCKET ASYNCHRONE & ULTRA-FAIBLE LATENCE
# ─────────────────────────────────────────────────────────────
class FrameStreamer:
    """
    Diffuseur de frames vidéo haute performance.
    Maintient une connexion WebSocket persistante vers le serveur vidéo
    avec élimination des frames obsolètes (latence temps réel < 20ms).
    """
    def __init__(self, target_url: str, auth_token: str = ""):
        self.target_url = target_url
        self.auth_token = auth_token
        self.frame_queue = queue.Queue(maxsize=2)
        self.running = True

        self.is_websocket = target_url.startswith("ws://") or target_url.startswith("wss://")
        self.thread = threading.Thread(target=self._worker, daemon=True, name="FrameStreamerWorker")
        self.thread.start()

    def send_frame(self, frame_bytes: bytes):
        """Enfile la dernière frame encodée en écrasant les précédentes si la file est pleine."""
        try:
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            self.frame_queue.put_nowait(frame_bytes)
        except Exception:
            pass

    def _worker(self):
        if self.is_websocket:
            asyncio.run(self._ws_sender_loop())
        else:
            self._http_sender_loop()

    async def _ws_sender_loop(self):
        import websockets

        url = self.target_url
        if self.auth_token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={urllib.parse.quote(self.auth_token)}"

        while self.running:
            try:
                logger.info(f"Connecting to Video WebSocket Hub at {self.target_url}...")
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=10 * 1024 * 1024
                ) as ws:
                    logger.info("Connected to Video WebSocket Hub as producer.")
                    while self.running:
                        try:
                            # Récupération non-bloquante de la dernière image
                            frame_data = await asyncio.get_event_loop().run_in_executor(
                                None, lambda: self.frame_queue.get(timeout=1.0)
                            )
                            if frame_data:
                                await ws.send(frame_data)
                        except queue.Empty:
                            continue
            except Exception as err:
                logger.warning(f"WebSocket publisher disconnected ({err}), reconnecting in 2s...")
                await asyncio.sleep(2)

    def _http_sender_loop(self):
        while self.running:
            try:
                frame_data = self.frame_queue.get(timeout=1.0)
                if frame_data:
                    b64_frame = "data:image/jpeg;base64," + base64.b64encode(frame_data).decode("utf-8")
                    payload = {"frame": b64_frame}
                    requests.post(self.target_url, json=payload, timeout=0.2)
            except queue.Empty:
                continue
            except Exception:
                time.sleep(1)


# ─────────────────────────────────────────────────────────────
# DÉTECTION DYNAMIQUE DE LA WEBCAM
# ─────────────────────────────────────────────────────────────
def find_camera_device(target_name="C920"):
    """Scanne /sys/class/video4linux/ ou /dev/video* pour identifier la caméra cible."""
    sys_v4l_path = "/sys/class/video4linux"

    if os.path.isdir(sys_v4l_path):
        video_dirs = sorted(
            glob.glob(os.path.join(sys_v4l_path, "video*")),
            key=lambda p: int(p.split("video")[-1]) if p.split("video")[-1].isdigit() else 999
        )
        for vdir in video_dirs:
            name_file = os.path.join(vdir, "name")
            if os.path.exists(name_file):
                try:
                    with open(name_file, "r") as f:
                        dev_name = f.read().strip()
                    if target_name.lower() in dev_name.lower():
                        vname = os.path.basename(vdir)
                        dev_path = f"/dev/{vname}"
                        test_cap = cv2.VideoCapture(dev_path, cv2.CAP_V4L2)
                        if test_cap.isOpened():
                            ret, _ = test_cap.read()
                            test_cap.release()
                            if ret:
                                logger.info(f"Caméra '{dev_name}' détectée sur {dev_path}")
                                return dev_path
                except Exception:
                    pass

    for dev_path in sorted(glob.glob("/dev/video*"), key=lambda p: int(p.replace("/dev/video", "")) if p.replace("/dev/video", "").isdigit() else 999):
        try:
            test_cap = cv2.VideoCapture(dev_path, cv2.CAP_V4L2)
            if test_cap.isOpened():
                ret, _ = test_cap.read()
                test_cap.release()
                if ret:
                    logger.info(f"Sélection automatique du périphérique vidéo : {dev_path}")
                    return dev_path
        except Exception:
            pass

    return None


# ─────────────────────────────────────────────────────────────
# TÉLÉCHARGEMENT AUTOMATIQUE DES MODÈLES SI NÉCESSAIRE
# ─────────────────────────────────────────────────────────────
def ensure_models_exist():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(FACES_DIR, exist_ok=True)
    os.makedirs(BLACKLIST_DIR, exist_ok=True)

    if not os.path.exists(YUNET_PATH):
        logger.info("[*] Téléchargement du détecteur de visages YuNet...")
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
        logger.info("[+] YuNet téléchargé.")

    if not os.path.exists(SFACE_PATH):
        logger.info("[*] Téléchargement du réseau de reconnaissance SFace...")
        urllib.request.urlretrieve(SFACE_URL, SFACE_PATH)
        logger.info("[+] SFace téléchargé.")


# ─────────────────────────────────────────────────────────────
# CHARGEMENT DES BASES DE VISAGES (AUTORISÉS & BLACKLIST)
# ─────────────────────────────────────────────────────────────
def load_face_database(directory_path, face_detector, face_recognizer, label_name="AUTORISÉ"):
    database = {}
    valid_exts = (".jpg", ".jpeg", ".png", ".bmp")

    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        return database

    files = [f for f in os.listdir(directory_path) if f.lower().endswith(valid_exts)]
    logger.info(f"Chargement de {len(files)} visage(s) [{label_name}]...")

    for filename in files:
        filepath = os.path.join(directory_path, filename)
        img = cv2.imread(filepath)
        if img is None:
            continue

        face_detector.setInputSize((img.shape[1], img.shape[0]))
        _, faces = face_detector.detect(img)

        if faces is not None and len(faces) > 0:
            aligned = face_recognizer.alignCrop(img, faces[0])
            feature = face_recognizer.feature(aligned)
            person_name = os.path.splitext(filename)[0].replace("_", " ").title()
            database[person_name] = feature
            logger.info(f"  [+] [{label_name}] Enregistré : {person_name}")
        else:
            logger.warning(f"  [!] Aucun visage détecté sur l'image [{label_name}] : {filename}")

    return database


# ─────────────────────────────────────────────────────────────
# 4. FONCTION : API REST
# ─────────────────────────────────────────────────────────────
def send_alert_rest(status_msg: str, box_coords: list, threat_name: str = "INTRUDER", level: str = "critical"):
    """
    Point d'entrée pour votre propre API Rest personnalisée.
    Appelé automatiquement en cas d'anomalie détectée (intrus, blacklisté, objet suspect).
    """
    # ── PLACEZ VOTRE PROPRE CODE D'APPEL API REST CI-DESSOUS ──
    # Exemple :
    # payload = {"level": level, "threat": threat_name, "message": status_msg, "box": box_coords}
    # requests.post("VOTRE_URL_API_REST", json=payload)
    pass


# ─────────────────────────────────────────────────────────────
# PROGRAMME PRINCIPAL
# ─────────────────────────────────────────────────────────────
def main():
    logger.info("=" * 70)
    logger.info("SENTINEL-X — DÉMARRAGE DU MODULE IA VISION & IDENTIFICATION")
    logger.info("=" * 70)

    ensure_models_exist()

    # 1. Chargement des modèles
    logger.info("Initialisation de YOLOv8n, YuNet & SFace...")
    yolo_model = YOLO("yolov8n.pt")

    face_detector = cv2.FaceDetectorYN.create(
        model=YUNET_PATH,
        config="",
        input_size=(FRAME_WIDTH, FRAME_HEIGHT),
        score_threshold=0.6
    )

    face_recognizer = cv2.FaceRecognizerSF.create(
        model=SFACE_PATH,
        config=""
    )

    # Chargement des bases de visages
    authorized_db = load_face_database(FACES_DIR, face_detector, face_recognizer, "AUTORISÉ")
    blacklist_db = load_face_database(BLACKLIST_DIR, face_detector, face_recognizer, "BLACKLISTÉ")

    # Initialisation du diffuseur vidéo vers le WebSocket
    streamer = FrameStreamer(STREAM_SERVER_URL, WS_AUTH_TOKEN)
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]

    # Initialisation de la capture caméra
    cap = None
    if DEVICE_CONFIG and DEVICE_CONFIG != "auto":
        target_dev = int(DEVICE_CONFIG) if DEVICE_CONFIG.isdigit() else DEVICE_CONFIG
    else:
        target_dev = find_camera_device(CAMERA_NAME)

    if target_dev is not None:
        logger.info(f"Ouverture du périphérique caméra : {target_dev}")
        cap = cv2.VideoCapture(target_dev, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(target_dev)

    if cap is None or not cap.isOpened():
        # Fallback index 0
        cap = cv2.VideoCapture(0)

    is_simulation = not cap.isOpened()
    if is_simulation:
        logger.warning("Aucune webcam physique détectée. Mode simulation activé.")
    else:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

    last_alert_time = 0
    feedback_msg = ""
    feedback_time = 0
    prev_frame_time = time.time()
    fps_display = 0.0
    frame_counter = 0

    window_name = "Sentinel-X — Analyse Video YOLOv8 & Reconnaissance"
    gui_active = ENABLE_GUI
    if gui_active:
        try:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        except Exception:
            gui_active = False

    logger.info("Surveillance IA active et diffusion vers le WebSocket démarrée.")

    try:
        while True:
            # 1. RÉCUPÉRATION DU FLUX
            if is_simulation:
                frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                cv2.putText(frame, "SIMULATION (Webcam absente)", (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
                time.sleep(1.0 / TARGET_FPS)
            else:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

            # 2. ANALYSER LE FLUX VIDÉO AVEC YOLOv8
            results = yolo_model(frame, verbose=False)

            critical_anomaly = False
            warning_anomaly = False
            highest_conf = 0.0
            alert_box = []
            current_faces_in_frame = []
            detected_threat_types = []

            # Détection des visages dans l'image globale
            face_detector.setInputSize((FRAME_WIDTH, FRAME_HEIGHT))
            _, detected_faces = face_detector.detect(frame)

            # 3. DÉTECTER LES ÉVÉNEMENTS OU ANOMALIES
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    if conf < CONFIDENCE_THRESHOLD:
                        continue

                    cls_id = int(box.cls[0])
                    class_name = yolo_model.names.get(cls_id, f"object_{cls_id}").lower()

                    if MONITORED_CLASSES and class_name not in MONITORED_CLASSES:
                        continue

                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())

                    if class_name == "person":
                        person_status = "TO_VERIFY"
                        matched_name = "INCONNU"
                        best_similarity = 0.0

                        if detected_faces is not None and len(detected_faces) > 0:
                            for f in detected_faces:
                                fx, fy, fw, fh = map(int, f[0:4])
                                if x1 <= fx + fw // 2 <= x2 and y1 <= fy + fh // 2 <= y2:
                                    current_faces_in_frame.append((f, frame.copy()))
                                    aligned_face = face_recognizer.alignCrop(frame, f)
                                    face_feature = face_recognizer.feature(aligned_face)

                                    # 1. Comparer avec AUTORISÉ
                                    for name, auth_feature in authorized_db.items():
                                        score = face_recognizer.match(
                                            face_feature,
                                            auth_feature,
                                            cv2.FaceRecognizerSF_FR_COSINE
                                        )
                                        if score > best_similarity:
                                            best_similarity = score
                                            if score >= SIMILARITY_THRESHOLD:
                                                person_status = "AUTHORIZED"
                                                matched_name = name

                                    # 2. Si pas autorisé, comparer avec BLACKLIST
                                    if person_status != "AUTHORIZED":
                                        best_black_score = 0.0
                                        for name, black_feature in blacklist_db.items():
                                            b_score = face_recognizer.match(
                                                face_feature,
                                                black_feature,
                                                cv2.FaceRecognizerSF_FR_COSINE
                                            )
                                            if b_score > best_black_score:
                                                best_black_score = b_score
                                                if b_score >= SIMILARITY_THRESHOLD:
                                                    person_status = "BLACKLISTED"
                                                    matched_name = name
                                                    best_similarity = b_score

                        # DÉCISION & AFFICHAGE
                        if person_status == "AUTHORIZED":
                            color = (0, 255, 0)
                            label = f"AUTHORIZED: {matched_name.upper()}"
                        elif person_status == "BLACKLISTED":
                            critical_anomaly = True
                            color = (0, 0, 255)
                            label = f"BLACKLISTED: {matched_name.upper()}"
                            detected_threat_types.append(f"BLACKLISTED ({matched_name.upper()})")
                            if conf > highest_conf:
                                highest_conf = conf
                                alert_box = [x1, y1, x2, y2]
                        else:
                            warning_anomaly = True
                            color = (0, 165, 255)
                            label = "A VERIFIER: NON REPERTORIE"
                            detected_threat_types.append("PERSONNE NON REPERTORIEE")
                            if conf > highest_conf:
                                highest_conf = conf
                                alert_box = [x1, y1, x2, y2]
                    else:
                        critical_anomaly = True
                        color = (0, 0, 255)
                        label = f"INTRUSION OBJECT: {class_name.upper()}"
                        detected_threat_types.append(class_name.upper())
                        if conf > highest_conf:
                            highest_conf = conf
                            alert_box = [x1, y1, x2, y2]

                    # Dessin rectangle & label
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label_w, label_h = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 2)[0]
                    cv2.rectangle(frame, (x1, max(0, y1 - 25)), (x1 + label_w + 10, max(25, y1)), color, -1)
                    text_color = (0, 0, 0) if (color == (0, 255, 0) or color == (0, 165, 255)) else (255, 255, 255)
                    cv2.putText(
                        frame,
                        label,
                        (x1 + 5, max(18, y1 - 7)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        text_color,
                        2
                    )

            # 4. DÉCLENCHEMENT DE L'ALERTE EN CAS D'ANOMALIE
            if critical_anomaly or warning_anomaly:
                now = time.time()
                if now - last_alert_time > ALERT_COOLDOWN_SEC:
                    last_alert_time = now
                    threat_summary = ", ".join(sorted(set(detected_threat_types))) or "ANOMALIE"
                    alert_level = "critical" if critical_anomaly else "warning"
                    print(f"[IA] 🚨 ÉVÉNEMENT [{alert_level.upper()}] : {threat_summary} !")
                    send_alert_rest(f"Détection périmétrique : {threat_summary}", alert_box, threat_summary, level=alert_level)

            # Bandeau de statut
            if critical_anomaly:
                threat_summary = ", ".join(sorted(set(detected_threat_types))) or "INTRUSION"
                status_text = f"STATUS: ALERTE CRITIQUE ({threat_summary})"
                status_color = (0, 0, 255)
            elif warning_anomaly:
                status_text = "STATUS: A VERIFIER (PERSONNE NON REPERTORIEE)"
                status_color = (0, 165, 255)
            elif len(results[0].boxes) > 0:
                status_text = "STATUS: ACCES AUTORISE (NOMINAL)"
                status_color = (0, 255, 0)
            else:
                status_text = "STATUS: ZONE NOMINALE (ALL CLEAR)"
                status_color = (255, 255, 255)

            # Calcul FPS
            current_frame_time = time.time()
            frame_counter += 1
            delta_t = current_frame_time - prev_frame_time
            if delta_t >= 0.5:
                fps_display = frame_counter / delta_t
                frame_counter = 0
                prev_frame_time = current_frame_time

            cv2.putText(frame, status_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
            cv2.putText(frame, f"FPS: {fps_display:.1f}", (520, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

            if time.time() - feedback_time < 3.0 and feedback_msg:
                cv2.putText(frame, feedback_msg, (15, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            # 5. DIFFUSION DU FLUX ANNOTÉ VERS LE WEBSOCKET EN TEMPS RÉEL
            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if success:
                streamer.send_frame(buffer.tobytes())

            # Affichage et gestion touches si GUI activé
            if gui_active:
                try:
                    cv2.imshow(window_name, frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord('q'), ord('Q'), ord('a'), ord('A'), 27):
                        logger.info("Arrêt utilisateur demandé.")
                        break
                    elif cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                        logger.info("Fenêtre fermée par l'utilisateur.")
                        break
                    elif key in (ord('e'), ord('E'), ord('s'), ord('S')):
                        if current_faces_in_frame:
                            face_data, captured_frame = current_faces_in_frame[0]
                            new_filename = f"personne_autorisee_{int(time.time())}.jpg"
                            save_path = os.path.join(FACES_DIR, new_filename)
                            fx, fy, fw, fh = map(int, face_data[0:4])
                            pad_x = max(0, fx - int(fw * 0.2))
                            pad_y = max(0, fy - int(fh * 0.2))
                            crop_w = min(captured_frame.shape[1] - pad_x, int(fw * 1.4))
                            crop_h = min(captured_frame.shape[0] - pad_y, int(fh * 1.4))
                            cv2.imwrite(save_path, captured_frame[pad_y:pad_y+crop_h, pad_x:pad_x+crop_w])
                            authorized_db = load_face_database(FACES_DIR, face_detector, face_recognizer, "AUTORISÉ")
                            feedback_msg = "[OK] Visage AUTORISE enregistre (VERT) !"
                            feedback_time = time.time()
                            logger.info(f"Visage autorisé enregistré : {save_path}")
                        else:
                            feedback_msg = "[!] Aucun visage net a enregistrer. Rapprochez-vous !"
                            feedback_time = time.time()
                    elif key in (ord('b'), ord('B')):
                        if current_faces_in_frame:
                            face_data, captured_frame = current_faces_in_frame[0]
                            new_filename = f"personne_blackliste_{int(time.time())}.jpg"
                            save_path = os.path.join(BLACKLIST_DIR, new_filename)
                            fx, fy, fw, fh = map(int, face_data[0:4])
                            pad_x = max(0, fx - int(fw * 0.2))
                            pad_y = max(0, fy - int(fh * 0.2))
                            crop_w = min(captured_frame.shape[1] - pad_x, int(fw * 1.4))
                            crop_h = min(captured_frame.shape[0] - pad_y, int(fh * 1.4))
                            cv2.imwrite(save_path, captured_frame[pad_y:pad_y+crop_h, pad_x:pad_x+crop_w])
                            blacklist_db = load_face_database(BLACKLIST_DIR, face_detector, face_recognizer, "BLACKLISTÉ")
                            feedback_msg = "[!] Visage BLACKLISTE enregistre (ROUGE) !"
                            feedback_time = time.time()
                            logger.info(f"Visage blacklisté enregistré : {save_path}")
                        else:
                            feedback_msg = "[!] Aucun visage net a blacklister. Rapprochez-vous !"
                            feedback_time = time.time()
                except Exception as gui_err:
                    logger.debug(f"GUI exception: {gui_err}")
                    gui_active = False

    except KeyboardInterrupt:
        logger.info("Interruption détectée.")
    finally:
        if not is_simulation and cap is not None:
            cap.release()
        if gui_active:
            cv2.destroyAllWindows()
        logger.info("Module IA arrêté.")


if __name__ == "__main__":
    main()
