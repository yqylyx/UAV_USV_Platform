package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
public class MockRuntimeCommandDispatcher implements RuntimeCommandDispatcher {

    @Override
    public CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request) {
        return CommandDispatchResult.acknowledged(
                "Mock 适配器已确认指令；当前未连接真实 ROS/Unity 指令通道"
        );
    }
}
