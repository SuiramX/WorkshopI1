import asyncio
import logging
import os
import cv2
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("VideoStreamer")

PORT = int(os.environ.get("PORT", 8765))
DEVICE = os.environ.get("DEVICE", "/dev/video0")
FPS = int(os.environ.get("FPS", 30))

connected_clients = set()
latest_frame_jpeg = None
clients_lock = asyncio.Lock()


async def capture_loop():
    """Captures frames from the video device and broadcasts JPEG bytes to WebSocket clients."""
    global latest_frame_jpeg

    device_target = int(DEVICE) if DEVICE.isdigit() else DEVICE
    logger.info(f"Opening video capture device: {device_target}")

    cap = cv2.VideoCapture(device_target)

    # Optional camera adjustments
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 70]

    while True:
        try:
            if not cap.isOpened():
                logger.warning(f"Device {device_target} not available, retrying in 2 seconds...")
                await asyncio.sleep(2)
                cap.open(device_target)
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Failed to grab frame from camera, retrying...")
                await asyncio.sleep(0.5)
                continue

            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                await asyncio.sleep(0.01)
                continue

            jpeg_bytes = buffer.tobytes()
            latest_frame_jpeg = jpeg_bytes

            async with clients_lock:
                clients = list(connected_clients)

            if clients:
                # Broadcast concurrently
                tasks = [client.send(jpeg_bytes) for client in clients]
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(1.0 / FPS)

        except Exception as err:
            logger.error(f"Error during video capture: {err}")
            await asyncio.sleep(1)

    cap.release()


async def ws_handler(websocket, *args, **kwargs):
    """Handles new WebSocket client connections."""
    client_ip = getattr(websocket, "remote_address", "unknown")
    logger.info(f"Client connected: {client_ip}")

    async with clients_lock:
        connected_clients.add(websocket)

    try:
        # Send latest frame immediately if available
        if latest_frame_jpeg is not None:
            await websocket.send(latest_frame_jpeg)

        # Keep connection open
        async for _ in websocket:
            pass
    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
        pass
    except Exception as err:
        logger.warning(f"WebSocket client exception: {err}")
    finally:
        async with clients_lock:
            connected_clients.discard(websocket)
        logger.info(f"Client disconnected: {client_ip}")


async def main():
    logger.info(f"Starting Video WebSocket Server on 0.0.0.0:{PORT} (Device: {DEVICE}, FPS: {FPS})...")
    asyncio.create_task(capture_loop())

    async with websockets.serve(ws_handler, "0.0.0.0", PORT, max_size=10 * 1024 * 1024):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Video streaming server stopped.")
