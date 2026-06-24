package com.uavusv.platform.module.device.dto.request;

import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record DeviceSaveRequest(
        @NotBlank(message = "设备编码不能为空")
        @Size(max = 64, message = "设备编码不能超过64个字符")
        String code,

        @NotBlank(message = "设备名称不能为空")
        @Size(max = 100, message = "设备名称不能超过100个字符")
        String name,

        @NotNull(message = "设备类型不能为空")
        DeviceType type,

        @NotNull(message = "设备状态不能为空")
        DeviceStatus status,

        @Size(max = 128, message = "主机地址不能超过128个字符")
        String host,

        @Min(value = 1, message = "端口必须大于0")
        @Max(value = 65535, message = "端口不能超过65535")
        Integer port,

        @Size(max = 128, message = "ROS命名空间不能超过128个字符")
        String rosNamespace,

        @Size(max = 500, message = "备注不能超过500个字符")
        String description
) {
}
