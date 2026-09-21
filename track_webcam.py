import cv2
import time
import threading
import csv
import json
import os
import urllib.request
import urllib.error

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ultralytics import YOLO


# ============================================================
# SETTINGS
# ============================================================

CAMERA_INDEX = 0

MODEL_PATH = "yolo11s.pt"

CONFIDENCE = 0.30

IMAGE_SIZE = 512

GRID_ROWS = 2
GRID_COLS = 2

LOW_DENSITY = 5
MEDIUM_DENSITY = 10
HIGH_DENSITY = 15

MOVEMENT_THRESHOLD = 3

TREND_HISTORY_SIZE = 10

ALERT_CONFIRM_FRAMES = 30

ALERT_COOLDOWN = 10


# ============================================================
# LIVE BACKEND CONNECTION
# ============================================================

BACKEND_URL = "https://crowd-intelligence-back.vercel.app"

CROWD_STATE_ENDPOINT = (
    f"{BACKEND_URL}/api/crowd-state"
)

EVENT_ID = "testing_phase"

CAMERA_NAME = "Camera 01 - Main Entrance"

CAMERA_SOURCE = "Laptop Webcam"

BACKEND_UPDATE_INTERVAL = 1.0


# ============================================================
# LOCAL VIDEO STREAM
# ============================================================

STREAM_HOST = "0.0.0.0"

STREAM_PORT = 8000

latest_jpeg = None

latest_jpeg_lock = threading.Lock()


class VideoStreamHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        # ----------------------------------------------------
        # VIDEO STREAM
        # ----------------------------------------------------

        if self.path == "/video_feed":

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "multipart/x-mixed-replace; boundary=frame"
            )

            self.send_header(
                "Cache-Control",
                "no-cache, no-store, must-revalidate"
            )

            self.send_header(
                "Pragma",
                "no-cache"
            )

            self.send_header(
                "Access-Control-Allow-Origin",
                "*"
            )

            self.end_headers()

            try:

                while True:

                    with latest_jpeg_lock:

                        frame_data = latest_jpeg

                    if frame_data is not None:

                        self.wfile.write(
                            b"--frame\r\n"
                        )

                        self.wfile.write(
                            b"Content-Type: image/jpeg\r\n\r\n"
                        )

                        self.wfile.write(
                            frame_data
                        )

                        self.wfile.write(
                            b"\r\n"
                        )

                    time.sleep(0.03)

            except (
                BrokenPipeError,
                ConnectionResetError
            ):

                pass

            return


        # ----------------------------------------------------
        # ROOT
        # ----------------------------------------------------

        if self.path == "/":

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )

            self.end_headers()

            self.wfile.write(
                b"AI Crowd Intelligence video stream is running.\n"
                b"Open /video_feed to view the processed camera."
            )

            return


        # ----------------------------------------------------
        # 404
        # ----------------------------------------------------

        self.send_response(404)

        self.end_headers()


    def log_message(
        self,
        format,
        *args
    ):

        return


def start_video_stream():

    server = ThreadingHTTPServer(

        (
            STREAM_HOST,
            STREAM_PORT
        ),

        VideoStreamHandler

    )

    thread = threading.Thread(

        target=server.serve_forever,

        daemon=True

    )

    thread.start()

    print(
        f"Video stream: "
        f"http://localhost:{STREAM_PORT}/video_feed"
    )

    return server


# ============================================================
# LOCAL STATE FILE
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.abspath(__file__)
)

STATE_FILE = os.path.join(
    PROJECT_ROOT,
    "crowd_state.json"
)


def save_crowd_state(state):

    """
    Save the latest crowd intelligence locally.
    """

    temp_file = STATE_FILE + ".tmp"

    try:

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state,
                file,
                indent=2
            )

        os.replace(
            temp_file,
            STATE_FILE
        )

    except OSError as error:

        print(
            f"Could not save crowd state: {error}"
        )


# ============================================================
# BACKEND UPLOADER
# ============================================================

class BackendUploader:

    def __init__(
        self,
        endpoint,
        interval=1.0
    ):

        self.endpoint = endpoint

        self.interval = interval

        self.latest_state = None

        self.lock = threading.Lock()

        self.running = True

        self.connected = False


    def update_state(self, state):

        with self.lock:

            self.latest_state = state


    def start(self):

        threading.Thread(

            target=self.run,

            daemon=True

        ).start()

        return self


    def run(self):

        while self.running:

            state = None

            with self.lock:

                if self.latest_state is not None:

                    state = self.latest_state.copy()


            if state is not None:

                self.send_state(state)


            time.sleep(
                self.interval
            )


    def send_state(self, state):

        try:

            payload = json.dumps(
                state
            ).encode("utf-8")


            request = urllib.request.Request(

                self.endpoint,

                data=payload,

                headers={
                    "Content-Type":
                        "application/json"
                },

                method="POST"

            )


            with urllib.request.urlopen(

                request,

                timeout=5

            ) as response:

                response.read()


            if not self.connected:

                print(
                    "Backend connection established."
                )


            self.connected = True


        except urllib.error.URLError as error:

            if self.connected:

                print(
                    f"Backend connection lost: {error}"
                )

            self.connected = False


        except Exception as error:

            self.connected = False

            print(
                f"Backend upload error: {error}"
            )


    def stop(self):

        self.running = False


# ============================================================
# CAMERA CLASS
# ============================================================

class Camera:

    def __init__(self, source=0):

        self.cap = cv2.VideoCapture(
            source
        )

        self.frame = None

        self.running = True


    def start(self):

        threading.Thread(

            target=self.update,

            daemon=True

        ).start()

        return self


    def update(self):

        while self.running:

            success, frame = self.cap.read()

            if success:

                self.frame = frame


    def read(self):

        return self.frame


    def stop(self):

        self.running = False

        self.cap.release()


# ============================================================
# TRACK STATE
# ============================================================

class TrackState:

    def __init__(self):

        self.frames = 0

        self.prev_center = None

        self.center = None

        self.movement = 0

        self.direction = "STATIONARY"


# ============================================================
# TRACK STORAGE
# ============================================================

tracks = {}


# ============================================================
# UPDATE TRACK
# ============================================================

def update_track(track_id, center):

    if track_id not in tracks:

        tracks[track_id] = TrackState()


    track = tracks[track_id]

    track.frames += 1

    track.prev_center = track.center

    track.center = center


    if track.prev_center is not None:

        dx = (
            center[0]
            - track.prev_center[0]
        )

        dy = (
            center[1]
            - track.prev_center[1]
        )


        track.movement = (
            dx ** 2
            + dy ** 2
        ) ** 0.5


        if (
            track.movement
            < MOVEMENT_THRESHOLD
        ):

            track.direction = "STATIONARY"


        elif abs(dx) > abs(dy):

            if dx > 0:

                track.direction = "RIGHT"

            else:

                track.direction = "LEFT"


        else:

            if dy > 0:

                track.direction = "DOWN"

            else:

                track.direction = "UP"


    return track


# ============================================================
# DENSITY FUNCTION
# ============================================================

def get_density(count):

    if count <= LOW_DENSITY:

        return "LOW"


    elif count <= MEDIUM_DENSITY:

        return "MEDIUM"


    elif count <= HIGH_DENSITY:

        return "HIGH"


    else:

        return "CRITICAL"


# ============================================================
# START CAMERA
# ============================================================

camera = Camera(
    CAMERA_INDEX
).start()


# ============================================================
# LOAD YOLO MODEL
# ============================================================

model = YOLO(
    MODEL_PATH
)


# ============================================================
# START BACKEND UPLOADER
# ============================================================

backend_uploader = BackendUploader(

    CROWD_STATE_ENDPOINT,

    BACKEND_UPDATE_INTERVAL

).start()


# ============================================================
# START VIDEO STREAM
# ============================================================

video_server = start_video_stream()


print()
print("==============================================")
print(" AI CROWD INTELLIGENCE ENGINE")
print("==============================================")
print(
    f"Backend: {BACKEND_URL}"
)
print(
    f"Camera:  {CAMERA_NAME}"
)
print(
    f"Event:   {EVENT_ID}"
)
print(
    f"Stream:  http://localhost:{STREAM_PORT}/video_feed"
)
print("==============================================")
print()


# ============================================================
# ZONE HISTORY
# ============================================================

zone_history = [

    []

    for _ in range(
        GRID_ROWS * GRID_COLS
    )

]


# ============================================================
# ALERT VARIABLES
# ============================================================

high_risk_frames = 0

last_alert_time = 0

alert_events = []


# ============================================================
# ALERT CSV FILE
# ============================================================

alert_file = open(

    os.path.join(
        PROJECT_ROOT,
        "alert_history.csv"
    ),

    "a",

    newline=""

)


alert_writer = csv.DictWriter(

    alert_file,

    fieldnames=[

        "time",

        "zone",

        "risk_score",

        "risk_level",

        "density",

        "trend",

        "congestion"

    ]

)


if alert_file.tell() == 0:

    alert_writer.writeheader()


# ============================================================
# NORMAL AI WINDOW
# ============================================================

WINDOW_NAME = (
    "AI Crowd Intelligence"
)


cv2.namedWindow(

    WINDOW_NAME,

    cv2.WINDOW_NORMAL

)


cv2.resizeWindow(

    WINDOW_NAME,

    1280,

    720

)


# ============================================================
# MAIN LOOP
# ============================================================

try:

    while True:

        frame = camera.read()


        if frame is None:

            continue


        # ====================================================
        # YOLO + BYTE TRACK
        # ====================================================

        results = model.track(

            frame,

            persist=True,

            classes=[0],

            conf=CONFIDENCE,

            imgsz=IMAGE_SIZE,

            tracker="bytetrack.yaml",

            device=0,

            half=True,

            verbose=False

        )


        # ====================================================
        # FRAME SIZE
        # ====================================================

        frame_height, frame_width = (
            frame.shape[:2]
        )


        # ====================================================
        # ZONE COUNTS
        # ====================================================

        zone_counts = [

            0

            for _ in range(
                GRID_ROWS * GRID_COLS
            )

        ]


        # ====================================================
        # ZONE FLOW
        # ====================================================

        zone_flow = [

            {

                "LEFT": 0,

                "RIGHT": 0,

                "UP": 0,

                "DOWN": 0,

                "STATIONARY": 0

            }

            for _ in range(
                GRID_ROWS * GRID_COLS
            )

        ]


        # ====================================================
        # PERSON DETECTION + TRACKING
        # ====================================================

        if results[0].boxes.id is not None:

            boxes = (

                results[0]

                .boxes

                .xyxy

                .cpu()

                .numpy()

            )


            track_ids = (

                results[0]

                .boxes

                .id

                .cpu()

                .numpy()

                .astype(int)

            )


            for box, track_id in zip(

                boxes,

                track_ids

            ):

                x1, y1, x2, y2 = map(

                    int,

                    box

                )


                # ------------------------------------------------
                # PERSON CENTER
                # ------------------------------------------------

                center_x = int(

                    (x1 + x2) / 2

                )


                center_y = int(

                    (y1 + y2) / 2

                )


                # ------------------------------------------------
                # UPDATE TRACK
                # ------------------------------------------------

                track = update_track(

                    track_id,

                    (
                        center_x,
                        center_y
                    )

                )


                # ------------------------------------------------
                # FIND ZONE
                # ------------------------------------------------

                zone_width = (

                    frame_width
                    / GRID_COLS

                )


                zone_height = (

                    frame_height
                    / GRID_ROWS

                )


                zone_x = int(

                    center_x
                    / zone_width

                )


                zone_y = int(

                    center_y
                    / zone_height

                )


                if zone_x >= GRID_COLS:

                    zone_x = (
                        GRID_COLS - 1
                    )


                if zone_y >= GRID_ROWS:

                    zone_y = (
                        GRID_ROWS - 1
                    )


                zone = (

                    zone_y
                    * GRID_COLS
                    + zone_x

                )


                # ------------------------------------------------
                # ZONE COUNT
                # ------------------------------------------------

                zone_counts[zone] += 1


                # ------------------------------------------------
                # ZONE FLOW
                # ------------------------------------------------

                zone_flow[zone][
                    track.direction
                ] += 1


                # ------------------------------------------------
                # PERSON BOX
                # ------------------------------------------------

                cv2.rectangle(

                    frame,

                    (x1, y1),

                    (x2, y2),

                    (0, 255, 0),

                    2

                )


                # ------------------------------------------------
                # TRACK ID
                # ------------------------------------------------

                cv2.putText(

                    frame,

                    f"ID: {track_id}",

                    (x1, y1 - 10),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.5,

                    (0, 255, 0),

                    2

                )


                # ------------------------------------------------
                # MOVEMENT DIRECTION
                # ------------------------------------------------

                cv2.putText(

                    frame,

                    track.direction,

                    (x1, y2 + 20),

                    cv2.FONT_HERSHEY_SIMPLEX,

                    0.45,

                    (255, 255, 0),

                    1

                )


        # ========================================================
        # CROWD TREND
        # ========================================================

        zone_trends = []


        for zone in range(

            GRID_ROWS * GRID_COLS

        ):

            zone_history[zone].append(

                zone_counts[zone]

            )


            if len(
                zone_history[zone]
            ) > TREND_HISTORY_SIZE:

                zone_history[zone].pop(0)


            if len(
                zone_history[zone]
            ) >= 2:

                change = (

                    zone_history[zone][-1]

                    -

                    zone_history[zone][0]

                )


                if change > 2:

                    trend = "INCREASING"


                elif change < -2:

                    trend = "DECREASING"


                else:

                    trend = "STABLE"

            else:

                trend = "STABLE"


            zone_trends.append(
                trend
            )


        # ========================================================
        # CONGESTION
        # ========================================================

        zone_congestion = []


        for zone in range(

            GRID_ROWS * GRID_COLS

        ):

            count = zone_counts[zone]

            density = get_density(
                count
            )

            trend = zone_trends[zone]

            flow = zone_flow[zone]


            moving_people = (

                flow["LEFT"]

                + flow["RIGHT"]

                + flow["UP"]

                + flow["DOWN"]

            )


            if (

                density in [
                    "HIGH",
                    "CRITICAL"
                ]

                and trend == "INCREASING"

                and moving_people > 0

            ):

                congestion = "HIGH"


            elif (

                density == "MEDIUM"

                and trend == "INCREASING"

            ):

                congestion = "MODERATE"


            else:

                congestion = "LOW"


            zone_congestion.append(
                congestion
            )


        # ========================================================
        # ZONE RISK SCORE
        # ========================================================

        zone_risk_scores = []


        for zone in range(

            GRID_ROWS * GRID_COLS

        ):

            density = get_density(

                zone_counts[zone]

            )

            trend = zone_trends[zone]

            congestion = (
                zone_congestion[zone]
            )


            risk = 0


            if density == "MEDIUM":

                risk += 20


            elif density == "HIGH":

                risk += 40


            elif density == "CRITICAL":

                risk += 60


            if trend == "INCREASING":

                risk += 20


            elif trend == "DECREASING":

                risk -= 10


            if congestion == "MODERATE":

                risk += 10


            elif congestion == "HIGH":

                risk += 20


            risk = max(

                0,

                min(100, risk)

            )


            zone_risk_scores.append(
                risk
            )


        # ========================================================
        # ZONE RISK LEVEL
        # ========================================================

        zone_risk_levels = []


        for risk in zone_risk_scores:

            if risk <= 25:

                level = "SAFE"


            elif risk <= 50:

                level = "MODERATE"


            elif risk <= 75:

                level = "HIGH"


            else:

                level = "CRITICAL"


            zone_risk_levels.append(
                level
            )


        # ========================================================
        # OVERALL RISK
        # ========================================================

        overall_risk = max(
            zone_risk_scores
        )


        if overall_risk <= 25:

            overall_risk_level = "SAFE"


        elif overall_risk <= 50:

            overall_risk_level = "MODERATE"


        elif overall_risk <= 75:

            overall_risk_level = "HIGH"


        else:

            overall_risk_level = "CRITICAL"


        # ========================================================
        # HIGHEST RISK ZONE
        # ========================================================

        highest_risk_zone = (

            zone_risk_scores.index(

                max(zone_risk_scores)

            )

        )


        highest_risk_score = (

            zone_risk_scores[
                highest_risk_zone
            ]

        )


        highest_risk_level = (

            zone_risk_levels[
                highest_risk_zone
            ]

        )


        # ========================================================
        # ALERT PERSISTENCE
        # ========================================================

        if overall_risk_level in [

            "HIGH",

            "CRITICAL"

        ]:

            high_risk_frames += 1


        else:

            high_risk_frames = 0


        # ========================================================
        # ALERT ENGINE
        # ========================================================

        current_time = time.time()


        if (

            high_risk_frames
            >= ALERT_CONFIRM_FRAMES

        ):

            if (

                current_time
                - last_alert_time
                >= ALERT_COOLDOWN

            ):

                if highest_risk_level == "CRITICAL":

                    alert_message = (

                        f"CRITICAL: Zone "
                        f"{highest_risk_zone} "
                        f"Risk "
                        f"{highest_risk_score}"

                    )


                elif highest_risk_level == "HIGH":

                    alert_message = (

                        f"HIGH RISK: Zone "
                        f"{highest_risk_zone} "
                        f"Risk "
                        f"{highest_risk_score}"

                    )


                else:

                    alert_message = (
                        "NO ALERT"
                    )


                # --------------------------------------------
                # HUMAN-READABLE TIME
                # --------------------------------------------

                alert_time = time.strftime(
                    "%d-%m-%Y %H:%M:%S"
                )


                # --------------------------------------------
                # CREATE ALERT EVENT
                # --------------------------------------------

                alert_event = {

                    "time": alert_time,

                    "zone": highest_risk_zone,

                    "risk_score":
                        highest_risk_score,

                    "risk_level":
                        highest_risk_level,

                    "density":
                        get_density(
                            zone_counts[
                                highest_risk_zone
                            ]
                        ),

                    "trend":
                        zone_trends[
                            highest_risk_zone
                        ],

                    "congestion":
                        zone_congestion[
                            highest_risk_zone
                        ]

                }


                # --------------------------------------------
                # STORE IN MEMORY
                # --------------------------------------------

                alert_events.append(
                    alert_event
                )


                # --------------------------------------------
                # SAVE TO CSV
                # --------------------------------------------

                alert_writer.writerow(
                    alert_event
                )


                alert_file.flush()


                # --------------------------------------------
                # UPDATE ALERT TIME
                # --------------------------------------------

                last_alert_time = (
                    current_time
                )


            else:

                alert_message = (
                    "ALERT COOLDOWN"
                )


        else:

            alert_message = "NO ALERT"


        # ========================================================
        # BUILD LIVE CROWD STATE
        # ========================================================

        total_people = sum(
            zone_counts
        )


        zones_data = []


        for zone in range(
            GRID_ROWS * GRID_COLS
        ):

            flow = zone_flow[zone]


            zones_data.append({

                "zone": zone,

                "people":
                    zone_counts[zone],

                "density":
                    get_density(
                        zone_counts[zone]
                    ),

                "flow":
                    flow,

                "dominant_direction":
                    max(
                        flow,
                        key=flow.get
                    ),

                "trend":
                    zone_trends[zone],

                "congestion":
                    zone_congestion[zone],

                "risk":
                    zone_risk_scores[zone],

                "risk_level":
                    zone_risk_levels[zone]

            })


        crowd_state = {

            "timestamp":
                time.strftime(
                    "%d-%m-%Y %H:%M:%S"
                ),

            "event_id":
                EVENT_ID,

            "camera_name":
                CAMERA_NAME,

            "camera_source":
                CAMERA_SOURCE,

            "camera_status":
                "LIVE",

            "total_people":
                total_people,

            "overall_risk":
                overall_risk,

            "overall_risk_level":
                overall_risk_level,

            "highest_risk_zone":
                highest_risk_zone,

            "highest_risk_score":
                highest_risk_score,

            "highest_risk_level":
                highest_risk_level,

            "alert":
                alert_message,

            "zones":
                zones_data

        }


        # ========================================================
        # SAVE LOCAL STATE
        # ========================================================

        save_crowd_state(
            crowd_state
        )


        # ========================================================
        # SEND STATE TO LIVE BACKEND
        # ========================================================

        backend_uploader.update_state(
            crowd_state
        )


        # ========================================================
        # DRAW ZONE GRID
        # ========================================================

        zone_width = int(

            frame_width
            / GRID_COLS

        )


        zone_height = int(

            frame_height
            / GRID_ROWS

        )


        for zone in range(

            GRID_ROWS * GRID_COLS

        ):

            zone_x = (
                zone % GRID_COLS
            )

            zone_y = (
                zone // GRID_COLS
            )


            x1 = (
                zone_x
                * zone_width
            )


            y1 = (
                zone_y
                * zone_height
            )


            x2 = (
                x1
                + zone_width
            )


            y2 = (
                y1
                + zone_height
            )


            # ------------------------------------------------
            # ZONE BORDER
            # ------------------------------------------------

            cv2.rectangle(

                frame,

                (x1, y1),

                (x2, y2),

                (255, 255, 255),

                1

            )


            # ------------------------------------------------
            # ZONE DATA
            # ------------------------------------------------

            count = zone_counts[zone]

            density = get_density(
                count
            )

            trend = zone_trends[zone]

            congestion = (
                zone_congestion[zone]
            )

            risk_score = (
                zone_risk_scores[zone]
            )

            risk_level = (
                zone_risk_levels[zone]
            )

            flow = zone_flow[zone]


            dominant_direction = max(

                flow,

                key=flow.get

            )


            # ------------------------------------------------
            # ZONE NUMBER
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Zone {zone}",

                (x1 + 10, y1 + 25),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.55,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # PEOPLE COUNT
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"People: {count}",

                (x1 + 10, y1 + 50),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.50,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # DENSITY
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Density: {density}",

                (x1 + 10, y1 + 75),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.50,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # FLOW
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Flow: {dominant_direction}",

                (x1 + 10, y1 + 100),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.45,

                (255, 255, 0),

                2

            )


            # ------------------------------------------------
            # TREND
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Trend: {trend}",

                (x1 + 10, y1 + 125),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.45,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # CONGESTION
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Congestion: {congestion}",

                (x1 + 10, y1 + 150),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.40,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # RISK SCORE
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Risk: {risk_score}",

                (x1 + 10, y1 + 175),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.50,

                (255, 255, 255),

                2

            )


            # ------------------------------------------------
            # RISK LEVEL
            # ------------------------------------------------

            cv2.putText(

                frame,

                f"Level: {risk_level}",

                (x1 + 10, y1 + 200),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.50,

                (255, 255, 255),

                2

            )


        # ========================================================
        # OVERALL RISK PANEL
        # ========================================================

        cv2.rectangle(

            frame,

            (10, 10),

            (310, 110),

            (0, 0, 0),

            -1

        )


        cv2.putText(

            frame,

            f"Overall Risk: {overall_risk}",

            (20, 38),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.60,

            (255, 255, 255),

            2

        )


        cv2.putText(

            frame,

            f"Status: {overall_risk_level}",

            (20, 65),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.55,

            (255, 255, 255),

            2

        )


        cv2.putText(

            frame,

            alert_message,

            (20, 95),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.50,

            (255, 255, 255),

            2

        )


        # ========================================================
        # BACKEND STATUS
        # ========================================================

        backend_status = (

            "BACKEND: CONNECTED"

            if backend_uploader.connected

            else "BACKEND: OFFLINE"

        )


        cv2.putText(

            frame,

            backend_status,

            (20, 135),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.50,

            (0, 255, 255),

            2

        )


        # ========================================================
        # ENCODE PROCESSED FRAME FOR VIDEO STREAM
        # ========================================================

        success, encoded_frame = cv2.imencode(

            ".jpg",

            frame,

            [
                cv2.IMWRITE_JPEG_QUALITY,
                80
            ]

        )


        if success:

            with latest_jpeg_lock:

                latest_jpeg = (
                    encoded_frame.tobytes()
                )


        # ========================================================
        # SHOW LOCAL AI WINDOW
        # ========================================================

        cv2.imshow(

            WINDOW_NAME,

            frame

        )


        # ========================================================
        # EXIT
        # ========================================================

        key = cv2.waitKey(1) & 0xFF


        if key == ord("q"):

            break


finally:

    # ========================================================
    # CLEANUP
    # ========================================================

    backend_uploader.stop()

    video_server.shutdown()

    video_server.server_close()

    camera.stop()

    cv2.destroyAllWindows()

    alert_file.close()

    print()
    print(
        "AI Crowd Intelligence Engine stopped."
    )