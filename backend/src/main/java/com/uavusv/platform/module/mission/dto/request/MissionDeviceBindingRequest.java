package com.uavusv.platform.module.mission.dto.request;

import com.uavusv.platform.module.mission.entity.MissionDeviceRole;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record MissionDeviceBindingRequest(
        @NotNull(message = "设备不能为空")
        Long deviceId,

        @NotNull(message = "设备角色不能为空")
        MissionDeviceRole role,

        @Size(max = 80, message = "呼号不能超过80个字符")
        String callSign,

        Boolean required,

        @Size(max = 500, message = "备注不能超过500个字符")
        String notes
) {
}
