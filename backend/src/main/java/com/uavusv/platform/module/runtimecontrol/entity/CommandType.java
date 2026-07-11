package com.uavusv.platform.module.runtimecontrol.entity;

public enum CommandType {
    START,
    STOP,
    TAKEOFF,
    LAND,
    START_MISSION,
    STOP_MISSION,
    PAUSE_MISSION,
    RESUME_MISSION,
    COMPLETE_MISSION,
    FAIL_MISSION,
    CANCEL_MISSION,
    SELECT_DEVICE,
    FOCUS_DEVICE,
    SWITCH_CAMERA,
    TOGGLE_TRAJECTORY
}
