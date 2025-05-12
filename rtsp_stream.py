import cv2
import gi
import threading
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

Gst.init(None)

class CameraStreamFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, cap, width=640, height=480, fps=30):
        super().__init__()
        self.cap = cap
        self.fps = fps
        self.width = width
        self.height = height
        self.number_frames = 0
        self.launch_string = (
            f'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME '
            f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1 ! '
            'videoconvert ! video/x-raw,format=I420 ! '
            'x264enc tune=zerolatency bitrate=500 speed-preset=superfast profile=main ! '
            'rtph264pay name=pay0 pt=96'
        )

    def on_need_data(self, src, length):
        ret, frame = self.cap.read()
        if not ret:
            print("프레임 수신 실패")
            return
        data = frame.tobytes()
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        duration = Gst.util_uint64_scale_int(1, Gst.SECOND, self.fps)
        timestamp = self.number_frames * duration
        buf.duration = duration
        buf.pts = buf.dts = timestamp
        buf.offset = timestamp
        self.number_frames += 1
        src.emit('push-buffer', buf)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        appsrc = rtsp_media.get_element().get_child_by_name("source")
        appsrc.connect("need-data", self.on_need_data)

class DualRTSPServer:
    def __init__(self, cap_thermal, cap_rgb):
        self.server = GstRtspServer.RTSPServer()
        mounts = self.server.get_mount_points()

        # 열화상 RTSP
        thermal_factory = CameraStreamFactory(cap_thermal)
        thermal_factory.set_shared(True)
        mounts.add_factory("/thermal", thermal_factory)

        # RGB RTSP (host pc rtsp 수신 → 다시 송출)
        rgb_factory = CameraStreamFactory(cap_rgb)
        rgb_factory.set_shared(True)
        mounts.add_factory("/rgb", rgb_factory)

        self.server.attach(None)
        print("RTSP 서버 실행 중:")
        print(" - 열화상: rtsp://192.168.1.103:8554/thermal")
        print(" - RGB   : rtsp://192.168.1.103:8554/rgb")

if __name__ == '__main__':
    # 열화상: USB 카메라
    cap_thermal = cv2.VideoCapture(0)
    if not cap_thermal.isOpened():
        print("열화상 카메라 열기 실패")
        exit(1)

    # RGB: 다른 PC에서 송출하는 RTSP 수신
    cap_rgb = cv2.VideoCapture('rtsp://192.168.1.120:8554/test')
    if not cap_rgb.isOpened():
        print("RGB RTSP 수신 실패")
        exit(1)

    server = DualRTSPServer(cap_thermal, cap_rgb)

    loop = GLib.MainLoop()
    loop.run()
