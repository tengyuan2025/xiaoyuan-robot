python3 << 'EOF'
from rplidar import RPLidar

lidar = RPLidar('/dev/ttyUSB1', baudrate=460800)  # C1 可能用 460800
lidar.start_motor()
import time
time.sleep(2)
print("电机应该开始转动了")
info = lidar.get_info()
print(f"设备信息: {info}")
lidar.stop_motor()
lidar.disconnect()
EOF

python3 << 'EOF'
import serial
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
print("监听中... 请说'小飞小飞'")
while True:
    data = ser.readline()
    if data:
        print(data.decode('utf-8', errors='ignore'))
EOF

python3 << 'EOF'
import cv2

print("检测摄像头...")
for i in range(12):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            filename = f'/root/camera_test_{i}.jpg'
            cv2.imwrite(filename, frame)
            h, w = frame.shape[:2]
            print(f"✓ /dev/video{i} 可用 ({w}x{h})，已保存 {filename}")
        else:
            print(f"? /dev/video{i} 打开但无法读取")
        cap.release()
EOF