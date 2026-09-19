"""Backend pipe integration fixture only. No real algorithm or Unity simulation."""
import argparse
import json
import sys
import threading

p = argparse.ArgumentParser()
p.add_argument('--algorithm')
p.add_argument('--run-id')
p.add_argument('--config-file')
p.add_argument('--fps')
p.add_argument('--command-protocol')
p.add_argument('--runtime-ref')
p.add_argument('--runtime-generation')
a = p.parse_args()
lock = threading.RLock()
state, version, heartbeat_sequence = 'PREPARED', 0, 0
identity = dict(protocolVersion='algorithm.command.v1', runtimeRef=a.runtime_ref,
                runtimeGeneration=a.runtime_generation)
cache = {}

def emit(message):
    with lock:
        print(json.dumps(message), flush=True)

def heartbeat():
    global heartbeat_sequence
    with lock:
        heartbeat_sequence += 1
        emit(dict(identity, kind='HEARTBEAT', heartbeatSequence=heartbeat_sequence,
                  runtimeState=state, stateVersion=version, lastFrameSequence=1))

emit(dict(identity, kind='RUNTIME_READY', adapterId='backend-test-only',
          capabilities=['START', 'PAUSE', 'RESUME', 'STOP'], state=state, stateVersion=version))
emit({'event': 'frame', 'payload': {'sequence': 1, 'agents': [
    {'deviceCode': 'UAV-001'}, {'deviceCode': 'USV-001'}]}})
heartbeat()
stop = threading.Event()
def beats():
    while not stop.wait(0.25):
        heartbeat()
threading.Thread(target=beats, daemon=True).start()
for line in sys.stdin:
    cmd = json.loads(line)
    with lock:
        if cmd['kind'] == 'STATUS_QUERY':
            emit(dict(identity, kind='STATUS_REPLY', queryId=cmd['queryId'],
                      commandId=cmd['commandId'], known=cmd['commandId'] in cache,
                      result=cache.get(cmd['commandId'])))
            continue
        if cmd['commandId'] in cache:
            emit(cache[cmd['commandId']])
            continue
        result = dict(identity, kind='COMMAND_RESULT', commandId=cmd['commandId'],
                      eventSequence=1, status='ACCEPTED', runtimeState=state,
                      stateVersion=version, lastFrameSequence=1, errorCode=None,
                      affectedDeviceCodes=['UAV-001', 'USV-001'])
        emit(result)
        state = {'START': 'RUNNING', 'PAUSE': 'PAUSED', 'RESUME': 'RUNNING', 'STOP': 'STOPPED'}[cmd['action']]
        version += 1
        result.update(status='SUCCEEDED', eventSequence=2, runtimeState=state, stateVersion=version)
        cache[cmd['commandId']] = result
        emit(result)
        if cmd['action'] == 'STOP':
            stop.set()
            break
