import subprocess
import time
import os

CSI_LEFT = "/base/axi/pcie@1000120000/rp1/i2c@88000/imx296@1a"
CSI_RIGHT = "/base/axi/pcie@1000120000/rp1/i2c@80000/imx296@1a"
USB_CENTER = "/dev/video0"

def start_camera(cmd, name):
    print(f"[{name}] Launching...")
    return subprocess.Popen(cmd, shell=True)

if __name__ == "__main__":
    try:
        os.system("sudo pkill -9 gst-launch-1.0")
        time.sleep(3)
        # left
        cmd_left = (
            f"gst-launch-1.0 libcamerasrc camera-name='{CSI_LEFT}' ! "
            "video/x-raw,format=NV12,width=480,height=640,framerate=10/1 ! "
            "videoconvert ! "
            #"video/x-raw,width=480,height=640 ! "
            "x264enc bitrate=800 tune=zerolatency speed-preset=ultrafast bframes=0 key-int-max=5 ! "
	    "video/x-h264,profile=baseline,stream-format=byte-stream ! "
	    "h264parse config-interval=1 ! "
            "queue max-size-buffers=2 leaky=downstream ! "
            "rtspclientsink location=rtsp://127.0.0.1:8554/left latency=0"
        )
        # right
        cmd_right = (
            f"gst-launch-1.0 libcamerasrc camera-name='{CSI_RIGHT}' ! "
            "video/x-raw,format=NV12,width=480,height=640,framerate=10/1 ! "
            "videoconvert ! "
            #"video/x-raw,width=480,height=640 ! "
            "x264enc bitrate=800 tune=zerolatency speed-preset=ultrafast bframes=0 key-int-max=5 ! "
            "video/x-h264,profile=baseline,stream-format=byte-stream ! "
	    "h264parse config-interval=1 ! "
            "queue max-size-buffers=2 leaky=downstream ! "
            "rtspclientsink location=rtsp://127.0.0.1:8554/right latency=0"
        )
        # centre usb cam so slightly different
        cmd_usb = (
            f"gst-launch-1.0 v4l2src device={USB_CENTER} io-mode=2 do-timestamp=true ! "
            "image/jpeg,framerate=10/1 ! jpegdec ! "
            "videoscale ! video/x-raw,width=480,height=640 ! "
            "videoconvert ! videoflip method=counterclockwise ! " # USB cam records in 4:3 only so i just rotate it to make it portrait resolution
            "x264enc bitrate=800 tune=zerolatency speed-preset=ultrafast bframes=0 key-int-max=5 ! "
            "video/x-h264,profile=baseline,stream-format=byte-stream ! "
	    "h264parse config-interval=1 ! "
            "queue max-size-buffers=2 leaky=downstream ! "
            "rtspclientsink location=rtsp://127.0.0.1:8554/center latency=0"
        )

        p_left = start_camera(cmd_left, "CSI Left")
        p_right = start_camera(cmd_right, "CSI Right")
        p_usb = start_camera(cmd_usb, "USB Center")

        while True:
              time.sleep(1)

    except KeyboardInterrupt:
        print("Stopping")
        os.system("sudo pkill -9 gst-launch-1.0")