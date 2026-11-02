"""
hand_tracking.py - webcam capture + MediaPipe hand landmarks on a background
thread.

Why a thread?  Reading a camera frame and running the hand model takes
15-30 ms.  If we did that inside Tkinter's event loop the whole window would
stutter.  Instead:

    camera thread                         Tkinter main thread (60 FPS)
    -------------                         ----------------------------
    read frame  -> mirror -> MediaPipe
    -> HandSample(21 landmarks) ---------> queue.Queue ---> GestureDetector
    -> small preview image  -------------> (lock)     ---> camera preview

The queue is thread-safe, so the two sides never touch the same data at the
same time.  The camera is *opened* on the main thread because macOS only
shows its camera-permission prompt for the main thread.
"""

import importlib.util
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass

from . import config

# Keep MediaPipe / TensorFlow-Lite start-up logs out of the terminal.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# Landmark indices we care about (MediaPipe numbering, 0 = wrist).
INDEX_TIP = 8

# Pairs of landmarks joined by lines in the preview "skeleton".
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),            # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),
)


@dataclass(frozen=True)
class HandSample:
    """One processed camera frame.

    landmarks: 21 (x, y) pairs normalised to 0..1 in the *mirrored* image,
               or None when no hand is visible.
    """
    timestamp: float
    landmarks: tuple = None
    handedness: str = None


class TrackerStatus:
    OFF = "off"
    STARTING = "starting"
    SEARCHING = "searching"     # camera running, no hand in view
    TRACKING = "tracking"       # hand found
    ERROR = "error"


class HandTracker:
    """Owns the webcam and the MediaPipe model; runs them on a daemon thread."""

    def __init__(self, camera_index=config.DEFAULT_CAMERA_INDEX, preview_enabled=True):
        self.camera_index = camera_index
        self.preview_enabled = preview_enabled
        self.samples = queue.Queue(maxsize=config.SAMPLE_QUEUE_SIZE)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._cap = None
        self._status = (TrackerStatus.OFF, "Camera off")
        self._preview = None
        self._preview_id = 0
        self._fps = 0.0

    # ---------------------------------------------------------------- control
    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """Open the camera and launch the worker thread.

        Returns True on success.  On failure the reason is available from
        ``status`` and the game keeps working with the mouse.
        """
        if self.running:
            return True
        self._stop_event.clear()
        self._drain_queue()
        self._set_status(TrackerStatus.STARTING, "Starting camera...")
        if importlib.util.find_spec("cv2") is None:   # missing package is not fatal
            self._set_status(TrackerStatus.ERROR,
                             "OpenCV missing - run: pip install -r requirements.txt")
            return False

        self._cap = self._open_camera()
        if self._cap is None:
            self._set_status(
                TrackerStatus.ERROR,
                f"Camera {self.camera_index} unavailable - check it is connected and "
                "that camera permission is granted")
            return False

        self._thread = threading.Thread(target=self._run, name="HandTracker", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Ask the worker to finish, wait for it and release the camera."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._release_camera()
        self._drain_queue()
        with self._lock:
            self._preview = None
        self._set_status(TrackerStatus.OFF, "Camera off")

    # --------------------------------------------------------------- read side
    @property
    def status(self):
        with self._lock:
            return self._status

    @property
    def fps(self):
        with self._lock:
            return self._fps

    def get_preview(self):
        """Return (frame_id, RGB numpy image) of the latest preview, or None."""
        with self._lock:
            if self._preview is None:
                return None
            return self._preview_id, self._preview

    def drain(self):
        """All samples produced since the last call (oldest first)."""
        items = []
        while True:
            try:
                items.append(self.samples.get_nowait())
            except queue.Empty:
                return items

    # ---------------------------------------------------------------- internals
    def _set_status(self, code, message):
        with self._lock:
            self._status = (code, message)

    def _drain_queue(self):
        self.drain()

    def _open_camera(self):
        import cv2
        backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else (
            cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY)
        try:
            cap = cv2.VideoCapture(self.camera_index, backend)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                cap.release()
                return None
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)     # always get the newest frame
            return cap
        except Exception:                            # cv2.error, backend problems
            return None

    def _release_camera(self):
        cap, self._cap = self._cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    def _push(self, sample):
        """Non-blocking put; if the game is not reading, drop the oldest sample."""
        try:
            self.samples.put_nowait(sample)
        except queue.Full:
            try:
                self.samples.get_nowait()
            except queue.Empty:
                pass
            try:
                self.samples.put_nowait(sample)
            except queue.Full:
                pass

    def _run(self):
        import cv2
        self._set_status(TrackerStatus.STARTING, "Loading hand-tracking model...")
        try:
            import mediapipe as mp
            hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=config.MP_MAX_HANDS,
                model_complexity=config.MP_MODEL_COMPLEXITY,
                min_detection_confidence=config.MP_DETECTION_CONFIDENCE,
                min_tracking_confidence=config.MP_TRACKING_CONFIDENCE,
            )
        except ImportError:
            self._set_status(TrackerStatus.ERROR,
                             "MediaPipe missing - run: pip install -r requirements.txt")
            self._release_camera()
            return
        except Exception as exc:  # AttributeError on incompatible versions, model errors
            self._set_status(TrackerStatus.ERROR, f"MediaPipe failed to start: {exc}")
            self._release_camera()
            return

        failures = 0
        got_first_frame = False
        last_reconnect = 0.0
        hand_visible = None
        fps_t0, fps_frames = time.perf_counter(), 0
        self._set_status(TrackerStatus.SEARCHING, "Show your hand to the camera")

        try:
            while not self._stop_event.is_set():
                cap = self._cap
                ok, frame = (cap.read() if cap is not None else (False, None))
                if not ok or frame is None:
                    failures += 1
                    if failures >= config.CAMERA_FAIL_LIMIT:
                        msg = ("Camera disconnected - reconnecting..." if got_first_frame else
                               "No video from camera - check camera permission")
                        self._set_status(TrackerStatus.ERROR, msg)
                        now = time.perf_counter()
                        if now - last_reconnect > config.CAMERA_RECONNECT_SECONDS:
                            last_reconnect = now
                            self._release_camera()
                            self._cap = self._open_camera()
                    time.sleep(0.03)
                    continue

                if failures >= config.CAMERA_FAIL_LIMIT or not got_first_frame:
                    self._set_status(TrackerStatus.SEARCHING, "Show your hand to the camera")
                    hand_visible = None
                failures = 0
                got_first_frame = True

                frame = cv2.flip(frame, 1)                       # mirror: move right = go right
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = hands.process(rgb)
                timestamp = time.perf_counter()

                landmarks, handed = None, None
                if result.multi_hand_landmarks:
                    hand = result.multi_hand_landmarks[0]
                    landmarks = tuple((lm.x, lm.y) for lm in hand.landmark)
                    if result.multi_handedness:
                        handed = result.multi_handedness[0].classification[0].label
                self._push(HandSample(timestamp, landmarks, handed))

                visible = landmarks is not None
                if visible != hand_visible:
                    hand_visible = visible
                    if visible:
                        self._set_status(TrackerStatus.TRACKING, "Hand tracked")
                    else:
                        self._set_status(TrackerStatus.SEARCHING, "Show your hand to the camera")

                if self.preview_enabled:
                    self._update_preview(cv2, rgb, landmarks)

                fps_frames += 1
                elapsed = timestamp - fps_t0
                if elapsed >= 1.0:
                    with self._lock:
                        self._fps = fps_frames / elapsed
                    fps_t0, fps_frames = timestamp, 0
        except Exception as exc:  # never let the worker die silently
            self._set_status(TrackerStatus.ERROR, f"Hand tracking stopped: {exc}")
        finally:
            hands.close()
            self._release_camera()

    def _update_preview(self, cv2, rgb, landmarks):
        w, h = config.PREVIEW_SIZE
        small = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        if landmarks:
            pts = [(int(x * w), int(y * h)) for x, y in landmarks]
            for a, b in HAND_CONNECTIONS:
                cv2.line(small, pts[a], pts[b], (54, 226, 255), 1, cv2.LINE_AA)
            for i, p in enumerate(pts):
                color = (255, 79, 163) if i == INDEX_TIP else (245, 243, 255)
                cv2.circle(small, p, 4 if i == INDEX_TIP else 2, color, -1, cv2.LINE_AA)
        with self._lock:
            self._preview = small
            self._preview_id += 1
