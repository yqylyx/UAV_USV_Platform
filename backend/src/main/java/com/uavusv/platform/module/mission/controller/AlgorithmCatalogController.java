package com.uavusv.platform.module.mission.controller;

import com.uavusv.platform.common.api.ApiResponse;
import com.uavusv.platform.module.mission.dto.response.AlgorithmDefinitionResponse;
import com.uavusv.platform.module.mission.service.AlgorithmCatalogService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/algorithms")
public class AlgorithmCatalogController {
    private final AlgorithmCatalogService service;

    public AlgorithmCatalogController(AlgorithmCatalogService service) { this.service = service; }

    @GetMapping
    public ApiResponse<List<AlgorithmDefinitionResponse>> list() { return ApiResponse.success(service.list()); }

    @PostMapping("/{code}/enabled")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmDefinitionResponse> setEnabled(@PathVariable String code, @RequestParam boolean enabled) {
        return ApiResponse.success(service.setEnabled(code, enabled));
    }

    @PostMapping("/{code}/default")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<AlgorithmDefinitionResponse> setDefault(@PathVariable String code) {
        return ApiResponse.success(service.setDefault(code));
    }
}
