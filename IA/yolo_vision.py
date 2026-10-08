import os
import time
import base64
import urllib.request
import requests
import cv2
import numpy as np
from ultralytics import YOLO

# ── CONFIGURATION ──
STREAM_SERVER_URL = os.getenv("STREAM_SERVER_URL", "http://localhost:8001")
API_FRAME_URL = f"{STREAM_SERVER_URL}/api/v1/video/frame"
CONFIDENCE_THRESHOLD = 0.50          # Seuil détection YOLOv8

_last_stream_time = 0.0


def stream_frame_to_websocket(frame, status_text: str, fps: float, threat_list: list):
    """
    Compresse la trame OpenCV annotée en binaire JPEG (base64)
    et la transmet au serveur WebSocket pour diffusion temps réel sur le Dashboard.
    """
    global _last_stream_time
    now = time.time()
    # Limite l'envoi à ~20 FPS (au moins 50 ms entre 2 images) pour ne pas saturer le réseau
    if now - _last_stream_time < 0.05:
        return
    _last_stream_time = now

    try:
        # Encodage binaire JPEG (qualité 50% pour un flux temps réel sous 30ms)
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        if not success:
            return

        b64_frame = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')
        payload = {
            "frame": b64_frame,
            "status": status_text,
            "fps": round(fps, 1),
            "threats": threat_list
        }
        # Envoi non bloquant avec timeout court
        requests.post(API_FRAME_URL, json=payload, timeout=0.15)
    except Exception:
        pass
SIMILARITY_THRESHOLD = 0.40          # Seuil cosinus SFace pour accréditation (>= 0.40 = même personne)
ALERT_COOLDOWN_SEC = 5.0             # Pause anti-spam entre alertes
FRAME_WIDTH = 640                    # Résolution VGA fluide < 100ms
FRAME_HEIGHT = 480

# Classes COCO surveillées :
# Détecte les humains + véhicules + électronique + sacs / armes.
# Définir sur None pour détecter TOUTES les 80 classes du modèle YOLOv8.
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
# TÉLÉCHARGEMENT AUTOMATIQUE DES MODÈLES SI NÉCESSAIRE
# ─────────────────────────────────────────────────────────────
def ensure_models_exist():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(FACES_DIR, exist_ok=True)
    os.makedirs(BLACKLIST_DIR, exist_ok=True)

    if not os.path.exists(YUNET_PATH):
        print("[*] Téléchargement du détecteur de visages YuNet...")
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
        print("[+] YuNet téléchargé.")

    if not os.path.exists(SFACE_PATH):
        print("[*] Téléchargement du réseau de reconnaissance SFace...")
        urllib.request.urlretrieve(SFACE_URL, SFACE_PATH)
        print("[+] SFace téléchargé.")


# ─────────────────────────────────────────────────────────────
# CHARGEMENT DES BASES DE VISAGES (AUTORISÉS & BLACKLIST)
# ─────────────────────────────────────────────────────────────
def load_face_database(directory_path, face_detector, face_recognizer, label_name="AUTORISÉ"):
    """
    Parcourt un dossier (authorized_faces/ ou blacklist/) et extrait le vecteur
    facial (embedding SFace) de chaque photo.
    """
    database = {}
    valid_exts = (".jpg", ".jpeg", ".png", ".bmp")

    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        return database

    files = [f for f in os.listdir(directory_path) if f.lower().endswith(valid_exts)]
    print(f"[*] Chargement de {len(files)} visage(s) [{label_name}]...")

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
            print(f"  [+] [{label_name}] Enregistré : {person_name}")
        else:
            print(f"  [!] Aucun visage détecté sur l'image [{label_name}] : {filename}")

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
    print("=" * 70)
    print("🛡️  SENTINEL-X — DÉMARRAGE DU MODULE IA VISION & IDENTIFICATION")
    print("=" * 70)

    ensure_models_exist()

    # 1. Chargement des modèles
    print("[*] Initialisation de YOLOv8n, YuNet & SFace...")
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

    # 1. RÉCUPÉRER LE FLUX VIDÉO
    print("[*] Connexion à la webcam USB (index 0)...")
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    is_simulation = not cap.isOpened()
    if is_simulation:
        print("[!] Aucune webcam physique détectée. Mode simulation activé.")

    last_alert_time = 0
    feedback_msg = ""
    feedback_time = 0
    prev_frame_time = time.time()
    fps_display = 0.0
    frame_counter = 0

    print("\n[+] Surveillance active !")
    print("    - Touche 'q' : Quitter")
    print("    - Touche 'e' : Enrôler / Autoriser le visage actuel (🟢 VERT)")
    print("    - Touche 'b' : Blacklister le visage actuel (🚨 ROUGE)")
    print("    - Visage non répertorié : Statut À VÉRIFIER (🟠 ORANGE)\n")

    window_name = "Sentinel-X — Analyse Video YOLOv8 & Reconnaissance"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        while True:
            # 1. RÉCUPÉRATION DU FLUX
            if is_simulation:
                frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
                cv2.putText(frame, "SIMULATION (Webcam absente)", (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
                time.sleep(0.04)
            else:
                ret, frame = cap.read()
                if not ret:
                    continue
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

            # 2. ANALYSER LE FLUX VIDÉO AVEC YOLOv8 (Classes multi-objets)
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

                    # Filtrage sur les classes surveillées
                    if MONITORED_CLASSES and class_name not in MONITORED_CLASSES:
                        continue

                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())

                    if class_name == "person":
                        person_status = "TO_VERIFY"  # "AUTHORIZED", "BLACKLISTED", "TO_VERIFY"
                        matched_name = "INCONNU"
                        best_similarity = 0.0

                        if detected_faces is not None and len(detected_faces) > 0:
                            for f in detected_faces:
                                fx, fy, fw, fh = map(int, f[0:4])
                                # Vérifier si le visage est à l'intérieur du corps détecté
                                if x1 <= fx + fw // 2 <= x2 and y1 <= fy + fh // 2 <= y2:
                                    current_faces_in_frame.append((f, frame.copy()))
                                    # Aligner et extraire les caractéristiques faciales
                                    aligned_face = face_recognizer.alignCrop(frame, f)
                                    face_feature = face_recognizer.feature(aligned_face)

                                    # 1. Comparer avec la base AUTORISÉE
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

                                    # 2. Si pas autorisé, comparer avec la base BLACKLIST
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

                        # DÉCISION & AFFICHAGE (3 ÉTATS)
                        if person_status == "AUTHORIZED":
                            # ✅ PERSONNE AUTORISÉE (VERT)
                            color = (0, 255, 0)
                            label = f"AUTHORIZED: {matched_name.upper()}"

                        elif person_status == "BLACKLISTED":
                            # 🚨 PERSONNE BLACKLISTÉE (ROUGE VIF)
                            critical_anomaly = True
                            color = (0, 0, 255)
                            label = f"BLACKLISTED: {matched_name.upper()}"
                            detected_threat_types.append(f"BLACKLISTED ({matched_name.upper()})")
                            if conf > highest_conf:
                                highest_conf = conf
                                alert_box = [x1, y1, x2, y2]

                        else:
                            # ⚠️ NI AUTORISÉ NI BLACKLISTÉ -> STATUT À VÉRIFIER (ORANGE)
                            warning_anomaly = True
                            color = (0, 165, 255)  # Orange BGR
                            label = "A VERIFIER: NON REPERTORIE"
                            detected_threat_types.append("PERSONNE NON REPERTORIEE")
                            if conf > highest_conf:
                                highest_conf = conf
                                alert_box = [x1, y1, x2, y2]
                    else:
                        # 🚨 OBJET INTRUS DÉTECTÉ (laptop, tv, couteau, etc.)
                        critical_anomaly = True
                        color = (0, 0, 255)  # Rouge pour intrusion d'objet
                        label = f"INTRUSION OBJECT: {class_name.upper()}"
                        detected_threat_types.append(class_name.upper())
                        if conf > highest_conf:
                            highest_conf = conf
                            alert_box = [x1, y1, x2, y2]

                    # Dessin du rectangle englobant
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    # Fond dynamique pour le texte
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

            # Bandeau de statut général
            if critical_anomaly:
                threat_summary = ", ".join(sorted(set(detected_threat_types))) or "INTRUSION"
                status_text = f"STATUS: ALERTE CRITIQUE ({threat_summary})"
                status_color = (0, 0, 255)  # Rouge
            elif warning_anomaly:
                status_text = "STATUS: A VERIFIER (PERSONNE NON REPERTORIEE)"
                status_color = (0, 165, 255)  # Orange
            elif len(results[0].boxes) > 0:
                status_text = "STATUS: ACCES AUTORISE (NOMINAL)"
                status_color = (0, 255, 0)  # Vert
            else:
                status_text = "STATUS: ZONE NOMINALE (ALL CLEAR)"
                status_color = (255, 255, 255)

            # Calcul du FPS réel glissant
            current_frame_time = time.time()
            frame_counter += 1
            delta_t = current_frame_time - prev_frame_time
            if delta_t >= 0.5:
                fps_display = frame_counter / delta_t
                frame_counter = 0
                prev_frame_time = current_frame_time

            # Incrustation du statut et des FPS
            cv2.putText(frame, status_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
            cv2.putText(frame, f"FPS: {fps_display:.1f}", (520, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

            # Message temporaire (ex: après enrôlement 'e')
            if time.time() - feedback_time < 3.0 and feedback_msg:
                cv2.putText(frame, feedback_msg, (15, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            # Diffusion temps réel vers le serveur WebSocket (binaire JPEG / Base64)
            stream_frame_to_websocket(frame, status_text, fps_display, detected_threat_types)

            # Affichage local OpenCV
            cv2.imshow(window_name, frame)

            # Gestion des touches clavier
            key = cv2.waitKey(1) & 0xFF

            # Quitter si 'q', 'Q', 'a', 'A' (pour claviers AZERTY), ou Echap (27)
            if key in (ord('q'), ord('Q'), ord('a'), ord('A'), 27):
                print("[*] Demande d'arrêt utilisateur reçue.")
                break

            # Quitter si clic sur la croix [X] de la fenêtre
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                print("[*] Fenêtre fermée par l'utilisateur.")
                break

            elif key in (ord('e'), ord('E'), ord('s'), ord('S')):
                # Enrôlement direct du visage présent dans AUTORISÉ (VERT)
                if current_faces_in_frame:
                    face_data, captured_frame = current_faces_in_frame[0]
                    new_filename = f"personne_autorisee_{int(time.time())}.jpg"
                    save_path = os.path.join(FACES_DIR, new_filename)

                    # Sauvegarde du crop
                    fx, fy, fw, fh = map(int, face_data[0:4])
                    pad_x = max(0, fx - int(fw * 0.2))
                    pad_y = max(0, fy - int(fh * 0.2))
                    crop_w = min(captured_frame.shape[1] - pad_x, int(fw * 1.4))
                    crop_h = min(captured_frame.shape[0] - pad_y, int(fh * 1.4))
                    cv2.imwrite(save_path, captured_frame[pad_y:pad_y+crop_h, pad_x:pad_x+crop_w])

                    # Recharger la base autorisée
                    authorized_db = load_face_database(FACES_DIR, face_detector, face_recognizer, "AUTORISÉ")
                    feedback_msg = "[OK] Visage AUTORISE enregistre (VERT) !"
                    feedback_time = time.time()
                    print(f"[+] Visage autorisé enregistré avec succès dans : {save_path}")
                else:
                    feedback_msg = "[!] Aucun visage net a enregistrer. Rapprochez-vous !"
                    feedback_time = time.time()

            elif key in (ord('b'), ord('B')):
                # Enrôlement direct du visage présent dans BLACKLIST (ROUGE)
                if current_faces_in_frame:
                    face_data, captured_frame = current_faces_in_frame[0]
                    new_filename = f"personne_blackliste_{int(time.time())}.jpg"
                    save_path = os.path.join(BLACKLIST_DIR, new_filename)

                    # Sauvegarde du crop
                    fx, fy, fw, fh = map(int, face_data[0:4])
                    pad_x = max(0, fx - int(fw * 0.2))
                    pad_y = max(0, fy - int(fh * 0.2))
                    crop_w = min(captured_frame.shape[1] - pad_x, int(fw * 1.4))
                    crop_h = min(captured_frame.shape[0] - pad_y, int(fh * 1.4))
                    cv2.imwrite(save_path, captured_frame[pad_y:pad_y+crop_h, pad_x:pad_x+crop_w])

                    # Recharger la base blacklist
                    blacklist_db = load_face_database(BLACKLIST_DIR, face_detector, face_recognizer, "BLACKLISTÉ")
                    feedback_msg = "[!] Visage BLACKLISTE enregistre (ROUGE) !"
                    feedback_time = time.time()
                    print(f"[+] Visage BLACKLISTÉ enregistré avec succès dans : {save_path}")
                else:
                    feedback_msg = "[!] Aucun visage net a blacklister. Rapprochez-vous !"
                    feedback_time = time.time()

    except KeyboardInterrupt:
        print("\n[*] Interruption clavier (Ctrl+C) détectée.")
    finally:
        if not is_simulation:
            cap.release()
        cv2.destroyAllWindows()
        print("[*] Module IA arrêté.")


if __name__ == "__main__":
    main()
