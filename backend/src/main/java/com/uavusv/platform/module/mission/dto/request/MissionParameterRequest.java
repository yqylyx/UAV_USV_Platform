package com.uavusv.platform.module.mission.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record MissionParameterRequest(
        @NotBlank(message = "参数键不能为空")
        @Size(max = 80, message = "参数键不能超过80个字符")
        String key,

        @Size(max = 500, message = "参数值不能超过500个字符")
        String value,

        @Size(max = 40, message = "单位不能超过40个字符")
        String unit,

        @Size(max = 255, message = "参数说明不能超过255个字符")
        String description
) {
}
