package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;

public interface RuntimeCommandDispatcher {
    CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request);
}
