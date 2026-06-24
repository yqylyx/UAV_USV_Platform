package com.uavusv.platform.module.system.service.impl;

import com.uavusv.platform.module.system.dto.response.PlatformComponentResponse;
import com.uavusv.platform.module.system.dto.response.SystemHealthResponse;
import com.uavusv.platform.module.system.repository.PlatformComponentRepository;
import com.uavusv.platform.module.system.service.SystemService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;

@Service
@Transactional(readOnly = true)
public class SystemServiceImpl implements SystemService {

    private final JdbcTemplate jdbcTemplate;
    private final PlatformComponentRepository componentRepository;
    private final String applicationName;

    public SystemServiceImpl(
            JdbcTemplate jdbcTemplate,
            PlatformComponentRepository componentRepository,
            @Value("${spring.application.name}") String applicationName
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.componentRepository = componentRepository;
        this.applicationName = applicationName;
    }

    @Override
    public SystemHealthResponse getHealth() {
        String databaseVersion = jdbcTemplate.queryForObject("SELECT VERSION()", String.class);
        return new SystemHealthResponse(
                "UP",
                applicationName,
                "UP",
                databaseVersion,
                Instant.now()
        );
    }

    @Override
    public List<PlatformComponentResponse> listComponents() {
        return componentRepository.findAll().stream()
                .map(PlatformComponentResponse::from)
                .toList();
    }
}
