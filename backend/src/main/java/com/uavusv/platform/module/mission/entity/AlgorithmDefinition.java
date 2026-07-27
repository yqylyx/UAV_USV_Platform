package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

@Entity
@Table(name = "algorithm_definition")
public class AlgorithmDefinition extends BaseEntity {

    @Column(nullable = false, unique = true, length = 64)
    private String code;
    @Column(nullable = false, length = 120)
    private String name;
    @Column(nullable = false, length = 32)
    private String version;
    @Enumerated(EnumType.STRING)
    @Column(name = "mission_type", nullable = false, length = 40)
    private MissionType missionType;
    @Column(name = "adapter_type", nullable = false, length = 40)
    private String adapterType;
    @Column(name = "device_scale", nullable = false, length = 40)
    private String deviceScale;
    @Column(nullable = false)
    private boolean enabled;
    @Column(name = "default_for_type", nullable = false)
    private boolean defaultForType;
    @Column(length = 500)
    private String description;

    protected AlgorithmDefinition() {}

    public String getCode() { return code; }
    public String getName() { return name; }
    public String getVersion() { return version; }
    public MissionType getMissionType() { return missionType; }
    public String getAdapterType() { return adapterType; }
    public String getDeviceScale() { return deviceScale; }
    public boolean isEnabled() { return enabled; }
    public boolean isDefaultForType() { return defaultForType; }
    public String getDescription() { return description; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public void setDefaultForType(boolean value) { this.defaultForType = value; }
}
