package com.uavusv.platform.module.algorithm.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

@Entity
@Table(name = "algorithm_assignment")
public class AlgorithmAssignment extends BaseEntity {

    @Column(name = "command_id", nullable = false, length = 64)
    private String commandId;

    @Column(name = "target_id", length = 64)
    private String targetId;

    @Column(name = "vehicle_id", nullable = false, length = 64)
    private String vehicleId;

    @Column(name = "vehicle_code", length = 64)
    private String vehicleCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private AlgorithmAssignmentRole role;

    @Column
    private Double x;

    @Column
    private Double y;

    @Column
    private Double z;

    @Column
    private Double heading;

    @Column(length = 1000)
    private String detail;

    protected AlgorithmAssignment() {
    }

    public AlgorithmAssignment(String commandId, String targetId, String vehicleId, String vehicleCode,
                               AlgorithmAssignmentRole role, Double x, Double y, Double z, Double heading, String detail) {
        this.commandId = commandId;
        this.targetId = targetId;
        this.vehicleId = vehicleId;
        this.vehicleCode = vehicleCode;
        this.role = role == null ? AlgorithmAssignmentRole.STANDBY : role;
        this.x = x;
        this.y = y;
        this.z = z;
        this.heading = heading;
        this.detail = detail;
    }

    public String getCommandId() { return commandId; }
    public String getTargetId() { return targetId; }
    public String getVehicleId() { return vehicleId; }
    public String getVehicleCode() { return vehicleCode; }
    public AlgorithmAssignmentRole getRole() { return role; }
    public Double getX() { return x; }
    public Double getY() { return y; }
    public Double getZ() { return z; }
    public Double getHeading() { return heading; }
    public String getDetail() { return detail; }
}
