import cv2
import threading

class stream:
    def __init__(self, src, is_csi=False):
        self.stopped = False
        self.frame = None
        self.cap = None

        if is_csi:
            pipeline = (
                f'libcamerasrc camera-name="{src}" ! '
                'video/x-raw, width=480, height=640, format=YUY2 ! '
                'videoconvert ! '
                'video/x-raw, format=BGR ! '
                'appsink drop=true'
            )
            self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self.cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if self.cap is None or not self.cap.isOpened():
            print(f"Error could not open camera source: {src}")
            self.stopped = True
            return

        ret, frame = self.cap.read()
        if ret:
            self.frame = frame

    def start(self):
        if not self.stopped:
            threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
            else:
                self.stopped = True

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        if self.cap:
            self.cap.release()

CAM_LEFT_PATH = "/base/axi/pcie@1000120000/rp1/i2c@88000/imx296@1a" 
CAM_RIGHT_PATH = "/base/axi/pcie@1000120000/rp1/i2c@80000/imx296@1a"
CAM_CENTER_PATH = "/dev/video0"    # changes depending on which port and when the camera is plugged in (bash 'v4l2-ctl --list-devices' to find its path)

cam_left = stream(src=CAM_LEFT_PATH, is_csi=True).start()
cam_right = stream(src=CAM_RIGHT_PATH, is_csi=True).start()
cam_centre = stream(src=CAM_CENTER_PATH, is_csi=False).start()

while True:
    f1 = cam_left.read()
    f2 = cam_right.read()
    f3 = cam_centre.read()

    if f1 is not None: cv2.imshow("CSI Left (IMX296)", f1)
    if f2 is not None: cv2.imshow("CSI Right (IMX296)", f2)
    if f3 is not None:
        f3 = cv2.rotate(f3, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.imshow("USB Global Shutter", f3)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam_left.stop()
cam_right.stop()
cam_centre.stop()
cv2.destroyAllWindows()
