import asyncio
import glob
import logging
import os
import threading
import time
import urllib.parse
import cv2
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("VideoStreamer")

PORT = int(os.environ.get("PORT", 8765))
CAMERA_NAME = os.environ.get("CAMERA_NAME", "C920")
DEVICE_CONFIG = os.environ.get("DEVICE", "auto")
FPS = int(os.environ.get("FPS", 25))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", 65))
WS_AUTH_TOKEN = os.environ.get("WS_AUTH_TOKEN", "")
MAX_CLIENTS = int(os.environ.get("MAX_CLIENTS", 5))


STREAM_MODE = os.environ.get("STREAM_MODE", "camera").lower()  # 'camera' (direct) or 'ia' (relay from IA module)


class FrameBuffer:
    """Thread-safe frame buffer holding the latest captured camera frame."""
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_data = None
        self.frame_id = 0
        self.active_listeners = 0

    def set_frame(self, data: bytes):
        with self.lock:
            self.frame_data = data
            self.frame_id += 1

    def get_latest(self):
        with self.lock:
            return self.frame_data, self.frame_id

    def add_listener(self):
        with self.lock:
            self.active_listeners += 1
            return self.active_listeners

    def remove_listener(self):
        with self.lock:
            self.active_listeners = max(0, self.active_listeners - 1)
            return self.active_listeners

    def listener_count(self):
        with self.lock:
            return self.active_listeners


frame_buffer = FrameBuffer()
connected_clients = set()
clients_lock = asyncio.Lock()


def extract_token(websocket):
    """Extracts authentication token from query string or request headers."""
    # 1. Check path / query string
    req_path = getattr(websocket, "path", None)
    if not req_path and hasattr(websocket, "request"):
        req_path = getattr(websocket.request, "path", "")
    req_path = req_path or ""

    parsed = urllib.parse.urlparse(req_path)
    query_params = urllib.parse.parse_qs(parsed.query)
    tokens = query_params.get("token", [])
    if tokens:
        return tokens[0]

    # 2. Check Authorization or X-Auth-Token headers
    headers = getattr(websocket, "request_headers", None) or getattr(getattr(websocket, "request", None), "headers", None)
    if headers:
        auth_header = headers.get("Authorization") or headers.get("X-Auth-Token")
        if auth_header:
            if auth_header.startswith("Bearer "):
                return auth_header[7:].strip()
            return auth_header.strip()

    return None


def find_camera_device(target_name="C920"):
    """
    Scans /sys/class/video4linux/ to dynamically locate the /dev/videoX device
    matching the given camera model name (e.g., 'HD Pro Webcam C920').
    """
    sys_v4l_path = "/sys/class/video4linux"
    
    # 1. Search by device name in sysfs
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
                                logger.info(f"Found '{dev_name}' on device node {dev_path}")
                                return dev_path
                except Exception as err:
                    logger.debug(f"Error checking {vdir}: {err}")

    # 2. Fallback: Scan all /dev/video* devices to find any working video capture node
    for dev_path in sorted(glob.glob("/dev/video*"), key=lambda p: int(p.replace("/dev/video", "")) if p.replace("/dev/video", "").isdigit() else 999):
        try:
            test_cap = cv2.VideoCapture(dev_path, cv2.CAP_V4L2)
            if test_cap.isOpened():
                ret, _ = test_cap.read()
                test_cap.release()
                if ret:
                    logger.info(f"Auto-selected working video device: {dev_path}")
                    return dev_path
        except Exception:
            pass

    return None


def camera_capture_worker():
    """
    Dedicated worker thread for camera capture in direct 'camera' mode.
    Prevents blocking the asyncio event loop and optimizes CPU usage.
    """
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    cap = None
    active_device = None

    logger.info("Direct camera capture worker thread started.")

    while True:
        try:
            # When no clients are connected, sleep to save Raspberry Pi CPU & power
            if frame_buffer.listener_count() == 0:
                time.sleep(0.2)
                continue

            # Check / re-establish camera connection
            if cap is None or not cap.isOpened():
                if DEVICE_CONFIG and DEVICE_CONFIG != "auto":
                    target = int(DEVICE_CONFIG) if DEVICE_CONFIG.isdigit() else DEVICE_CONFIG
                else:
                    target = find_camera_device(CAMERA_NAME)

                if target is None:
                    logger.warning(f"Webcam '{CAMERA_NAME}' not found, retrying in 2 seconds...")
                    time.sleep(2)
                    continue

                logger.info(f"Attempting to open camera on {target}...")
                cap = cv2.VideoCapture(target, cv2.CAP_V4L2)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(target)

                if not cap.isOpened():
                    logger.warning(f"Failed to open {target}, retrying in 2 seconds...")
                    cap = None
                    time.sleep(2)
                    continue

                # Optimize stream parameters for smooth streaming & low latency
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, FPS)
                # Keep internal buffer to 1 frame to prevent queueing lag
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                active_device = target
                logger.info(f"Connected to camera on {active_device} (target {FPS} FPS, JPEG quality {JPEG_QUALITY})")

            # Read frame (blocking hardware read in dedicated thread)
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning(f"Failed to read frame from {active_device}, disconnecting to re-scan...")
                cap.release()
                cap = None
                active_device = None
                time.sleep(1)
                continue

            # Encode to JPEG
            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if success:
                frame_buffer.set_frame(buffer.tobytes())

        except Exception as err:
            logger.error(f"Error in camera capture thread: {err}")
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                active_device = None
            time.sleep(1)


async def ws_handler(websocket, *args, **kwargs):
    """Handles WebSocket connections for both consumers (viewers) and producers (IA module)."""
    client_ip = getattr(websocket, "remote_address", "unknown")

    # 1. Enforce authentication if WS_AUTH_TOKEN is set
    if WS_AUTH_TOKEN:
        token = extract_token(websocket)
        if token != WS_AUTH_TOKEN:
            logger.warning(f"Unauthorized connection attempt rejected from {client_ip}")
            try:
                await websocket.close(code=4401, reason="Unauthorized: Invalid or missing token")
            except Exception:
                pass
            return

    # 2. Extract request path
    req_path = getattr(websocket, "path", None)
    if not req_path and hasattr(websocket, "request"):
        req_path = getattr(websocket.request, "path", "")
    req_path = req_path or ""
    parsed_path = urllib.parse.urlparse(req_path).path

    # 3. Handle IA Producer connection (/publish, /ws/publish, /input, /push)
    if parsed_path in ("/publish", "/ws/publish", "/input", "/ws/input", "/push"):
        logger.info(f"IA Video Producer connected from {client_ip} on path '{parsed_path}'")
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    frame_buffer.set_frame(message)
                elif isinstance(message, str):
                    try:
                        import base64
                        import json
                        if message.startswith("{"):
                            data = json.loads(message)
                            b64 = data.get("frame", "")
                            if b64.startswith("data:image"):
                                b64 = b64.split(",", 1)[1]
                            frame_buffer.set_frame(base64.b64decode(b64))
                        else:
                            frame_buffer.set_frame(base64.b64decode(message))
                    except Exception as parse_err:
                        logger.debug(f"Could not parse string frame from producer: {parse_err}")
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as err:
            logger.warning(f"IA Video Producer connection error: {err}")
        finally:
            logger.info(f"IA Video Producer disconnected: {client_ip}")
        return

    # 4. Handle Video Consumer client (dashboard/browser viewers)
    async with clients_lock:
        if len(connected_clients) >= MAX_CLIENTS:
            logger.warning(f"Connection rejected from {client_ip}: maximum client limit ({MAX_CLIENTS}) reached")
            try:
                await websocket.close(code=4429, reason="Too many connections")
            except Exception:
                pass
            return
        connected_clients.add(websocket)

    active_count = frame_buffer.add_listener()
    logger.info(f"Client authenticated and connected: {client_ip} (Active clients: {active_count})")

    last_sent_id = -1
    frame_interval = 1.0 / max(1, FPS)

    try:
        # Stream loop for this client
        while True:
            frame_data, frame_id = frame_buffer.get_latest()
            if frame_data is not None and frame_id != last_sent_id:
                last_sent_id = frame_id
                await websocket.send(frame_data)

            await asyncio.sleep(frame_interval)

    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
        pass
    except Exception as err:
        logger.warning(f"WebSocket client exception: {err}")
    finally:
        active_count = frame_buffer.remove_listener()
        async with clients_lock:
            connected_clients.discard(websocket)
        logger.info(f"Client disconnected: {client_ip} (Active clients: {active_count})")


async def main():
    mode_desc = "IA Stream Relay (Annotated Feed)" if STREAM_MODE in ("ia", "ai", "relay") else "Direct Camera Capture"
    logger.info(f"Starting Video WebSocket Server on 0.0.0.0:{PORT} [Mode: {STREAM_MODE.upper()} - {mode_desc}]...")
    if WS_AUTH_TOKEN:
        logger.info("Security: Token authentication is ENABLED.")
    else:
        logger.warning("Security: WS_AUTH_TOKEN is not configured! All connections will be allowed.")

    # Start direct camera worker thread only if in 'camera' mode
    if STREAM_MODE in ("camera", "direct", "raw"):
        logger.info(f"Mode is '{STREAM_MODE}': launching local camera capture worker.")
        worker_thread = threading.Thread(target=camera_capture_worker, daemon=True, name="CameraCaptureWorker")
        worker_thread.start()
    else:
        logger.info(f"Mode is '{STREAM_MODE}': waiting for IA module to publish annotated video frames on /publish.")

    async with websockets.serve(ws_handler, "0.0.0.0", PORT, max_size=10 * 1024 * 1024, ping_interval=20, ping_timeout=20):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Video streaming server stopped.")
