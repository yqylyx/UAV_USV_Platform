"""Explicit authorized local sample -> real HTTP ASR. Output stays outside Git by default.
This is NOT browser/Java/mxy acceptance. Starts and terminates only its own ASR child.
"""
import argparse
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid

import av
from asr_server import decode_audio
from test_asr_server import encoded_silence


def encode(samples, format='webm', codec='libopus'):
    output = io.BytesIO()
    with av.open(output, mode='w', format=format) as container:
        stream = container.add_stream(codec, rate=48000)
        stream.layout = 'mono'
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=48000)
        for start in range(0, len(samples), 1600):
            frame = av.AudioFrame.from_ndarray(samples[start:start + 1600].reshape(1, -1), format='fltp', layout='mono')
            frame.sample_rate = 16000
            for converted in resampler.resample(frame):
                for packet in stream.encode(converted):
                    container.mux(packet)
        for converted in resampler.resample(None):
            for packet in stream.encode(converted):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--output', required=True, help='Private JSON output, do not commit transcripts without consent')
    parser.add_argument('--normalize-damaged-source', action='store_true', help='Explicit diagnostic only: re-encode a damaged source in memory; also test original rejection')
    args = parser.parse_args()
    raw = Path(args.audio).read_bytes()
    if args.normalize_damaged_source:
        from faster_whisper.audio import decode_audio as permissive_decode
        samples = permissive_decode(io.BytesIO(raw), sampling_rate=16000)
        duration = len(samples) * 1000 / 16000
    else:
        samples, duration = decode_audio(raw, 'audio/mpeg', time.monotonic() + 10)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = dict(os.environ, ASR_SERVICE_TOKEN=token, ASR_MODEL_PATH=args.model_path,
               ASR_CPU_THREADS='4', ASR_PORT=str(port), HF_HUB_OFFLINE='1', PYTHONIOENCODING='utf-8')
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('asr_server.py'))],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    rows = []
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('ASR child exited before ready')
            try:
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                conn.request('GET', '/health/ready')
                response = conn.getresponse()
                response.read()
                conn.close()
                if response.status == 200:
                    break
            except OSError:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('ASR did not become ready within 90 seconds')
        cases = [
            ('authorized-mp3', raw, 'audio/mpeg', 415 if args.normalize_damaged_source else 200),
            ('same-recording-webm', encode(samples), 'audio/webm;codecs=opus', 200),
            ('synthetic-silence', encoded_silence(2), 'audio/mpeg', 422),
        ]
        if args.normalize_damaged_source:
            cases.insert(1, ('explicitly-normalized-mp3', encode(samples, 'mp3', 'libmp3lame'), 'audio/mpeg', 200))
        for name, audio, mime, expected in cases:
            request_id = str(uuid.uuid4())
            boundary = secrets.token_hex(16)
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="requestId"\r\n\r\n{request_id}'
                    f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="locale"\r\n\r\nzh-CN'
                    f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="sample"\r\nContent-Type: {mime}\r\n\r\n').encode()
            body += audio + f'\r\n--{boundary}--\r\n'.encode()
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=125)
            started = time.perf_counter()
            conn.request('POST', '/internal/asr/transcriptions', body, {
                'Authorization': 'Bearer ' + token, 'X-ASR-Timeout-Ms': '120000',
                'Content-Type': 'multipart/form-data; boundary=' + boundary,
            })
            response = conn.getresponse()
            result = json.loads(response.read())
            conn.close()
            row = {'sample': name, 'status': response.status, 'seconds': time.perf_counter() - started, 'response': result}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            assert response.status == expected
            assert result['requestId'] == request_id
            if expected == 422:
                assert result['code'] == 'ASR_NO_SPEECH'
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        print('Owned ASR child exited; pid=' + str(process.pid), flush=True)
    report = {'scope': 'nly development only: real Python HTTP, not Java/browser acceptance',
              'cpu_threads': 4, 'offline_hub': True, 'audio_sha256': hashlib.sha256(raw).hexdigest(),
              'explicit_normalization': args.normalize_damaged_source,
              'durationMs': duration, 'results': rows, 'asr_child_exited': process.poll() is not None}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
