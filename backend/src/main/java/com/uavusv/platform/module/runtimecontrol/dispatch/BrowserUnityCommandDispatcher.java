package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "app.control.command-dispatch-mode", havingValue = "browser-unity")
public class BrowserUnityCommandDispatcher implements RuntimeCommandDispatcher {
    @Override
    public CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request) {
        return CommandDispatchResult.dispatched(
                "指令已登记，等待浏览器 Unity WebGL 返回真实执行确认"
        );
    }
}
