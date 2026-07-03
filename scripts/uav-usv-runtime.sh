#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/tmp/uav_usv_platform"
ROS_LOG_DIR="$RUNTIME_DIR/logs"
DEMO_PID_FILE="$RUNTIME_DIR/demo.pid"
BRIDGE_PID_FILE="$RUNTIME_DIR/bridge.pid"

mkdir -p "$ROS_LOG_DIR"

is_managed_running() {
    local pid_file="$1"
    [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

is_external_running() {
    local pattern="$1"
    pgrep -f "$pattern" >/dev/null 2>&1
}

start_process() {
    local name="$1"
    local pid_file="$2"
    local command="$3"

    if is_managed_running "$pid_file"; then
        echo "$name=managed:$(cat "$pid_file")"
        return
    fi

    : >"$ROS_LOG_DIR/$name.log"
    nohup setsid bash -lc "echo '[platform] starting $name at '\"\$(date -Is)\"; $command" >"$ROS_LOG_DIR/$name.log" 2>&1 < /dev/null &
    local pid=$!
    echo "$pid" > "$pid_file"
    for _ in {1..10}; do
        if is_managed_running "$pid_file"; then
            echo "$name=started:$pid"
            return
        fi
        sleep 0.5
    done
    echo "$name=failed"
    tail -n 40 "$ROS_LOG_DIR/$name.log" || true
    return 1
}

start_runtime() {
    local setup="cd ~/UAV_USV && source /opt/ros/humble/setup.bash && if [[ -f ~/ros_tcp_ws/install/setup.bash ]]; then source ~/ros_tcp_ws/install/setup.bash; fi && source ~/UAV_USV/install/setup.bash"
    local px4_dir="${PX4_DIR:-$HOME/PX4-Autopilot}"

    if is_external_running "ros2 launch uav_usv_sim uav_usv_cooperation_demo.launch.py"; then
        echo "demo=external"
    else
        start_process "demo" "$DEMO_PID_FILE" "$setup && ros2 launch uav_usv_sim uav_usv_cooperation_demo.launch.py land_on_deck:=false px4_dir:=$px4_dir"
    fi

    if is_external_running "ros2 launch uav_usv_sim uav_usv_unity_websocket_bridge.launch.py"; then
        echo "bridge=external"
    else
        start_process "bridge" "$BRIDGE_PID_FILE" "$setup && ros2 launch uav_usv_sim uav_usv_unity_websocket_bridge.launch.py"
    fi
}

cleanup_runtime_leftovers() {
    pkill -f "gz sim .*PX4-Autopilot/Tools/simulation/gz/worlds/default.sdf" >/dev/null 2>&1 || true
    pkill -f "make px4_sitl gz_x500" >/dev/null 2>&1 || true
    pkill -f "PX4-Autopilot.*/bin/px4" >/dev/null 2>&1 || true
    pkill -f "parameter_bridge" >/dev/null 2>&1 || true
    pkill -f "rviz2" >/dev/null 2>&1 || true
    pkill -f "cooperative_lighthouse_mission" >/dev/null 2>&1 || true
}

stop_process() {
    local name="$1"
    local pid_file="$2"
    if ! is_managed_running "$pid_file"; then
        rm -f "$pid_file"
        echo "$name=not-managed"
        return
    fi

    local pid
    pid="$(cat "$pid_file")"
    kill -INT -- "-$pid" 2>/dev/null || kill -INT "$pid" 2>/dev/null || true
    for _ in {1..10}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
    echo "$name=stopped"
}

status_runtime() {
    if is_managed_running "$DEMO_PID_FILE"; then echo "demo=managed:$(cat "$DEMO_PID_FILE")";
    elif is_external_running "ros2 launch uav_usv_sim uav_usv_cooperation_demo.launch.py"; then echo "demo=external";
    else echo "demo=stopped"; fi

    if is_managed_running "$BRIDGE_PID_FILE"; then echo "bridge=managed:$(cat "$BRIDGE_PID_FILE")";
    elif is_external_running "ros2 launch uav_usv_sim uav_usv_unity_websocket_bridge.launch.py"; then echo "bridge=external";
    else echo "bridge=stopped"; fi
}

case "${1:-status}" in
    start) start_runtime ;;
    stop)
        stop_process "bridge" "$BRIDGE_PID_FILE"
        stop_process "demo" "$DEMO_PID_FILE"
        cleanup_runtime_leftovers
        ;;
    status) status_runtime ;;
    *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
