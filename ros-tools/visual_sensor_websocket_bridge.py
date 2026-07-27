#!/usr/bin/env python3
"""Six-channel ROS 2 compressed-image to WebSocket gateway.

This is an additive platform integration tool. It does not modify the Unity
simulation or mission controllers. The frontend backend connects on port 8766;
the existing pose/control bridge remains isolated on port 8765.
"""

import base64
import hashlib
import json
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


DEFAULT_CAMERA_IDS = [
    'uav_01', 'uav_02', 'uav_03',
    'usv_01', 'usv_02', 'usv_03',
]
DEFAULT_CAMERA_TOPICS = [
    '/uav_usv/uav_01/camera/image/compressed',
    '/uav_usv/uav_02/camera/image/compressed',
    '/uav_usv/uav_03/camera/image/compressed',
    '/uav_usv/usv_01/camera/image/compressed',
    '/uav_usv/usv_02/camera/image/compressed',
    '/uav_usv/usv_03/camera/image/compressed',
]


@dataclass
class ClientSession:
    connection: socket.socket
    camera_ids: set = field(default_factory=lambda: set(DEFAULT_CAMERA_IDS))
    focused_camera_id: str = 'uav_01'
    thumbnail_fps: float = 2.0
    focused_fps: float = 12.0
    last_sent: dict = field(default_factory=dict)
    send_lock: threading.Lock = field(default_factory=threading.Lock)


class VisualSensorWebSocketBridge(Node):
    def __init__(self):
        super().__init__('visual_sensor_websocket_bridge')
        self.declare_parameter('ws_host', '0.0.0.0')
        self.declare_parameter('ws_port', 8766)
        self.declare_parameter('camera_ids', DEFAULT_CAMERA_IDS)
        self.declare_parameter('camera_topics', DEFAULT_CAMERA_TOPICS)
        self.declare_parameter('max_jpeg_bytes', 1_500_000)

        self.host = str(self.get_parameter('ws_host').value)
        self.port = int(self.get_parameter('ws_port').value)
        self.max_jpeg_bytes = int(self.get_parameter('max_jpeg_bytes').value)
        camera_ids = list(self.get_parameter('camera_ids').value)
        camera_topics = list(self.get_parameter('camera_topics').value)
        if len(camera_ids) != len(camera_topics):
            raise ValueError('camera_ids and camera_topics must have the same length')

        self.running = True
        self.server_socket = None
        self.clients = []
        self.clients_lock = threading.Lock()
        self.subscriptions = []
        for camera_id, topic in zip(camera_ids, camera_topics):
            subscription = self.create_subscription(
                CompressedImage,
                topic,
                lambda message, selected=camera_id: self._on_image(selected, message),
                2,
            )
            self.subscriptions.append(subscription)
            self.get_logger().info(f'Camera {camera_id}: {topic}')

        self.server_thread = threading.Thread(
            target=self._serve,
            name='visual-sensor-websocket-server',
            daemon=True,
        )
        self.server_thread.start()
        self.get_logger().info(
            f'Visual sensor gateway listening on ws://{self.host}:{self.port}/visual_sensors'
        )

    def _on_image(self, camera_id, message):
        jpeg = bytes(message.data)
        if not jpeg or len(jpeg) > self.max_jpeg_bytes:
            return
        stamp = message.header.stamp
        timestamp_ms = int(stamp.sec * 1000 + stamp.nanosec / 1_000_000)
        if timestamp_ms <= 0:
            timestamp_ms = int(time.time() * 1000)
        frame = {
            'type': 'camera_frame',
            'camera_id': camera_id,
            'encoding': 'jpeg',
            'timestamp_ms': timestamp_ms,
            'source': 'ROS / Gazebo',
            'jpeg_base64': base64.b64encode(jpeg).decode('ascii'),
        }
        encoded = self._encode_text_frame(json.dumps(frame, separators=(',', ':')))
        now = time.monotonic()
        dead = []
        with self.clients_lock:
            sessions = list(self.clients)
        for session in sessions:
            if camera_id not in session.camera_ids:
                continue
            fps = session.focused_fps if camera_id == session.focused_camera_id else session.thumbnail_fps
            interval = 1.0 / max(0.2, fps)
            if now - session.last_sent.get(camera_id, 0.0) < interval:
                continue
            try:
                with session.send_lock:
                    session.connection.sendall(encoded)
                session.last_sent[camera_id] = now
            except OSError:
                dead.append(session)
        self._remove_clients(dead)

    def _serve(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            self.server_socket = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(8)
            server.settimeout(0.5)
            while self.running:
                try:
                    connection, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                connection.settimeout(2.0)
                if not self._handshake(connection):
                    connection.close()
                    continue
                connection.settimeout(None)
                session = ClientSession(connection)
                with self.clients_lock:
                    self.clients.append(session)
                threading.Thread(
                    target=self._receive_client,
                    args=(session,),
                    name=f'visual-sensor-client-{address[0]}',
                    daemon=True,
                ).start()

    def _receive_client(self, session):
        try:
            while self.running:
                text = self._read_text_frame(session.connection)
                if text is None:
                    break
                payload = json.loads(text)
                if payload.get('type') != 'sensor_subscription':
                    continue
                requested = payload.get('camera_ids', DEFAULT_CAMERA_IDS)
                session.camera_ids = set(item for item in requested if item in DEFAULT_CAMERA_IDS)
                focus = payload.get('focused_camera_id', session.focused_camera_id)
                if focus in DEFAULT_CAMERA_IDS:
                    session.focused_camera_id = focus
                session.thumbnail_fps = min(5.0, max(0.2, float(payload.get('thumbnail_fps', 2))))
                session.focused_fps = min(20.0, max(1.0, float(payload.get('focused_fps', 12))))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            self._remove_clients([session])

    @staticmethod
    def _handshake(connection):
        try:
            request = b''
            while b'\r\n\r\n' not in request and len(request) < 8192:
                chunk = connection.recv(1024)
                if not chunk:
                    return False
                request += chunk
            key = None
            for header in request.decode('utf-8', errors='ignore').split('\r\n'):
                if header.lower().startswith('sec-websocket-key:'):
                    key = header.split(':', 1)[1].strip()
                    break
            if not key:
                return False
            accept = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()
            ).digest()).decode()
            connection.sendall((
                'HTTP/1.1 101 Switching Protocols\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Accept: {accept}\r\n\r\n'
            ).encode('ascii'))
            return True
        except OSError:
            return False

    @staticmethod
    def _read_exact(connection, length):
        data = b''
        while len(data) < length:
            chunk = connection.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _read_text_frame(self, connection):
        header = self._read_exact(connection, 2)
        if header is None:
            return None
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            extra = self._read_exact(connection, 2)
            if extra is None:
                return None
            length = struct.unpack('!H', extra)[0]
        elif length == 127:
            extra = self._read_exact(connection, 8)
            if extra is None:
                return None
            length = struct.unpack('!Q', extra)[0]
        mask = self._read_exact(connection, 4) if masked else None
        payload = self._read_exact(connection, length)
        if payload is None or opcode == 8:
            return None
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return payload.decode('utf-8') if opcode == 1 else ''

    @staticmethod
    def _encode_text_frame(text):
        payload = text.encode('utf-8')
        length = len(payload)
        if length < 126:
            header = bytes([0x81, length])
        elif length <= 0xFFFF:
            header = bytes([0x81, 126]) + struct.pack('!H', length)
        else:
            header = bytes([0x81, 127]) + struct.pack('!Q', length)
        return header + payload

    def _remove_clients(self, sessions):
        if not sessions:
            return
        with self.clients_lock:
            self.clients = [item for item in self.clients if item not in sessions]
        for session in sessions:
            try:
                session.connection.close()
            except OSError:
                pass

    def destroy_node(self):
        self.running = False
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass
        with self.clients_lock:
            sessions = list(self.clients)
            self.clients.clear()
        self._remove_clients(sessions)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VisualSensorWebSocketBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
