import asyncio
import glob
import logging
import os
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
FPS = int(os.environ.get("FPS", 30))
WS_AUTH_TOKEN = os.environ.get("WS_AUTH_TOKEN", "")
MAX_CLIENTS = int(os.environ.get("MAX_CLIENTS", 5))

connected_clients = set()
latest_frame_jpeg = None
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
                        # Test if this specific node can produce video frames
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


async def capture_loop():
    """Captures real camera frames and broadcasts JPEG bytes to connected WebSocket clients."""
    global latest_frame_jpeg

    cap = None
    active_device = None
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 75]

    while True:
        try:
            # 1. Check/re-establish camera connection
            if cap is None or not cap.isOpened():
                if DEVICE_CONFIG and DEVICE_CONFIG != "auto":
                    target = int(DEVICE_CONFIG) if DEVICE_CONFIG.isdigit() else DEVICE_CONFIG
                else:
                    target = find_camera_device(CAMERA_NAME)

                if target is None:
                    logger.warning(f"Webcam '{CAMERA_NAME}' not found, retrying in 2 seconds...")
                    await asyncio.sleep(2)
                    continue

                logger.info(f"Attempting to open camera on {target}...")
                cap = cv2.VideoCapture(target, cv2.CAP_V4L2)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(target)

                if not cap.isOpened():
                    logger.warning(f"Failed to open {target}, retrying in 2 seconds...")
                    cap = None
                    await asyncio.sleep(2)
                    continue

                # Optimize stream parameters for Logitech C920
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, FPS)
                active_device = target
                logger.info(f"Connected to camera on {active_device} at {FPS} FPS")

            # 2. Read frame
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning(f"Failed to read frame from {active_device}, disconnecting to re-scan...")
                cap.release()
                cap = None
                active_device = None
                await asyncio.sleep(1)
                continue

            # 3. Compress frame as JPEG
            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                await asyncio.sleep(0.01)
                continue

            jpeg_bytes = buffer.tobytes()
            latest_frame_jpeg = jpeg_bytes

            # 4. Broadcast to clients
            async with clients_lock:
                clients = list(connected_clients)

            if clients:
                tasks = [client.send(jpeg_bytes) for client in clients]
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(1.0 / FPS)

        except Exception as err:
            logger.error(f"Error in capture loop: {err}")
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
            await asyncio.sleep(1)

    if cap:
        cap.release()


async def ws_handler(websocket, *args, **kwargs):
    """Handles new WebSocket client connections with authentication and limits."""
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

    # 2. Enforce concurrent client limit
    async with clients_lock:
        if len(connected_clients) >= MAX_CLIENTS:
            logger.warning(f"Connection rejected from {client_ip}: maximum client limit ({MAX_CLIENTS}) reached")
            try:
                await websocket.close(code=4429, reason="Too many connections")
            except Exception:
                pass
            return
        connected_clients.add(websocket)

    logger.info(f"Client authenticated and connected: {client_ip} (Active clients: {len(connected_clients)})")

    try:
        if latest_frame_jpeg is not None:
            await websocket.send(latest_frame_jpeg)

        async for _ in websocket:
            pass
    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
        pass
    except Exception as err:
        logger.warning(f"WebSocket client exception: {err}")
    finally:
        async with clients_lock:
            connected_clients.discard(websocket)
        logger.info(f"Client disconnected: {client_ip} (Active clients: {len(connected_clients)})")


async def main():
    logger.info(f"Starting Video WebSocket Server on 0.0.0.0:{PORT} (Auto-target: '{CAMERA_NAME}')...")
    if WS_AUTH_TOKEN:
        logger.info("Security: Token authentication is ENABLED.")
    else:
        logger.warning("Security: WS_AUTH_TOKEN is not configured! All connections will be allowed.")
    asyncio.create_task(capture_loop())

    async with websockets.serve(ws_handler, "0.0.0.0", PORT, max_size=10 * 1024 * 1024):
        await asyncio.Future()



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Video streaming server stopped.")
