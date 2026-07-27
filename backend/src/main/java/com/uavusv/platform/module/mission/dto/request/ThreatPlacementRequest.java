package com.uavusv.platform.module.mission.dto.request;

import jakarta.validation.constraints.NotNull;

public record ThreatPlacementRequest(@NotNull Double x, @NotNull Double y) {}
