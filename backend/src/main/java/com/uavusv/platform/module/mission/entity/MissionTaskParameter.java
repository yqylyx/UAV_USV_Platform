package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "mission_task_parameter")
public class MissionTaskParameter extends BaseEntity {

    @Column(name = "mission_id", nullable = false)
    private Long missionId;

    @Column(name = "param_key", nullable = false, length = 80)
    private String key;

    @Column(name = "param_value", length = 500)
    private String value;

    @Column(name = "param_unit", length = 40)
    private String unit;

    @Column(length = 255)
    private String description;

    protected MissionTaskParameter() {
    }

    public MissionTaskParameter(Long missionId, String key, String value, String unit, String description) {
        this.missionId = missionId;
        this.key = key;
        this.value = value;
        this.unit = unit;
        this.description = description;
    }

    public Long getMissionId() {
        return missionId;
    }

    public String getKey() {
        return key;
    }

    public String getValue() {
        return value;
    }

    public String getUnit() {
        return unit;
    }

    public String getDescription() {
        return description;
    }
}
