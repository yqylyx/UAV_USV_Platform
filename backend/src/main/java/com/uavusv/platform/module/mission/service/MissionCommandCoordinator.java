package com.uavusv.platform.module.mission.service;

import com.uavusv.platform.module.runtimecontrol.event.ControlCommandStatusChangedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class MissionCommandCoordinator {

    private final MissionRuntimeReconciler missionRuntimeReconciler;

    public MissionCommandCoordinator(MissionRuntimeReconciler missionRuntimeReconciler) {
        this.missionRuntimeReconciler = missionRuntimeReconciler;
    }

    @EventListener
    @Transactional
    public void handleCommandStatus(ControlCommandStatusChangedEvent event) {
        missionRuntimeReconciler.reconcileCommandStatus(event);
    }
}
