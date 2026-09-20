import cv2
import time
import threading 
from ultralytics import YOLO

PHONE_STREAME = " "

class CameraStream :
    def __int__(self,url):
        self.url=url
        self.cap=cv2.VideoCapture(url)

        self.lock = threading.Lock()
        self.lock = None 
        self.running = True 

        self.thread = threading.Thread(
            target = self.update, 
            daemon = True
        )
        self.thread.start()

    def update(self):
        while self.running:
            success, frame = self.cap.read()

            if success:
                with self.lock:
                    self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is None:
                return False,None

            return True, self.frame.copy()

    def stop(self):
        self.running = False 
        self.cap.release()

camera = CameraStream(PHONE_STREAME)

model = YOLO("yolo11s.pt")

DETECTION_TNTERNAL =0.08
last_detection = 0

last_result = None 

fps_counter  = 0 
fps_timer = time.time()
display_fps = 0 

while True:
    success, frame = camera.read()

    if not success:
        time.sleep(0.01)
        continue
    now = time.time()

    if now - last_detection >= DETECTION_TNTERNAL:
        results = model(
            frame,
            device = 0,
            classes=[0],
            conf = 0.30,
            imgsz = 640,
            werbose = False 
        )
        last_result = results[0]
        last_detection = now 

        if last_result  is not None:
            output = last_result.plot()
        else: 
            output = frame 
    fps_counter +=1
    elapsed = time.time() - fps_timer

    if elapsed >=1.0:
        display_fps = fps_counter / elapsed 
        fps_counter = 0
        fps_timer - time.time()

    cv2.putText(
        output,
        f"Display FPS: {display_fps:.1ff}",
        (20,35),
        cv2.FONT_HERSHEY_SIPLEX,
        0.8,
        (0,255,0),
        2

    )

    cv2.putText(
        output,
        "YOLO11s | PERSON ONLY | GPU",
        (20,70),
        cv2.FONT_HERSHEY_SIPLEX,
        0.7,
        (0,255,0),
        2
    )
    cv2.imshowd(
        " AI Crowd - Low Latency Detenciton ",
        output
    )
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.stop()
cv2.destroyAllWindows()
    

        

