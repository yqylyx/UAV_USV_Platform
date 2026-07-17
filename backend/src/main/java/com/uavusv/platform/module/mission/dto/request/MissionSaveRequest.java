package com.uavusv.platform.module.mission.dto.request;

import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionExecutionMode;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDateTime;
import java.util.List;

public record MissionSaveRequest(
        @NotBlank(message = "任务编号不能为空")
        @Size(max = 64, message = "任务编号不能超过64个字符")
        String code,

        @NotBlank(message = "任务名称不能为空")
        @Size(max = 120, message = "任务名称不能超过120个字符")
        String name,

        @NotNull(message = "任务类型不能为空")
        MissionType type,

        @NotNull(message = "任务运行模式不能为空")
        MissionExecutionMode executionMode,

        @NotNull(message = "任务状态不能为空")
        MissionStatus status,

        @NotNull(message = "任务阶段不能为空")
        MissionStage stage,

        @Min(value = 1, message = "优先级最小为1")
        @Max(value = 5, message = "优先级最大为5")
        Integer priority,

        @Size(max = 120, message = "目标名称不能超过120个字符")
        String targetName,

        @Size(max = 255, message = "目标行为不能超过255个字符")
        String targetBehavior,

        @Size(max = 255, message = "任务区域不能超过255个字符")
        String missionArea,

        LocalDateTime plannedStartAt,

        LocalDateTime plannedEndAt,

        @Size(max = 1000, message = "任务说明不能超过1000个字符")
        String description,

        @Valid
        List<MissionDeviceBindingRequest> devices,

        @Valid
        List<MissionParameterRequest> parameters
) {
}
