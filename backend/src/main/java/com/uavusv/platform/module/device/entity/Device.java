package com.uavusv.platform.module.device.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "mission_device")
public class Device extends BaseEntity {

    @Column(nullable = false, unique = true, length = 64)
    private String code;

    @Column(nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private DeviceType type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private DeviceStatus status;

    @Column(length = 128)
    private String host;

    private Integer port;

    @Column(name = "ros_namespace", length = 128)
    private String rosNamespace;

    @Column(length = 500)
    private String description;

    @Column(nullable = false)
    private boolean deleted;

    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

    protected Device() {
    }

    public Device(
            String code,
            String name,
            DeviceType type,
            DeviceStatus status,
            String host,
            Integer port,
            String rosNamespace,
            String description
    ) {
        update(code, name, type, status, host, port, rosNamespace, description);
    }

    public void update(
            String code,
            String name,
            DeviceType type,
            DeviceStatus status,
            String host,
            Integer port,
            String rosNamespace,
            String description
    ) {
        this.code = code;
        this.name = name;
        this.type = type;
        this.status = status;
        this.host = host;
        this.port = port;
        this.rosNamespace = rosNamespace;
        this.description = description;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public DeviceType getType() {
        return type;
    }

    public DeviceStatus getStatus() {
        return status;
    }

    public String getHost() {
        return host;
    }

    public Integer getPort() {
        return port;
    }

    public String getRosNamespace() {
        return rosNamespace;
    }

    public String getDescription() {
        return description;
    }

    public void updateRuntimeStatus(DeviceStatus status) {
        this.status = status;
    }

    public void softDelete() {
        this.deleted = true;
        this.deletedAt = LocalDateTime.now();
    }

    public boolean isDeleted() {
        return deleted;
    }
}
