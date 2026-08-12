package com.uavusv.platform.module.runtimecontrol.entity;

public enum CommandStatus {
    PENDING,
    DISPATCHED,
    ACCEPTED,
    EXECUTING,
    SUCCEEDED,
    FAILED,
    TIMEOUT,
    CANCELLED
}
