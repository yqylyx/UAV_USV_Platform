package com.uavusv.platform.module.mission.service;

import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.mission.dto.response.AlgorithmDefinitionResponse;
import com.uavusv.platform.module.mission.entity.AlgorithmDefinition;
import com.uavusv.platform.module.mission.repository.AlgorithmDefinitionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class AlgorithmCatalogService {
    private final AlgorithmDefinitionRepository repository;

    public AlgorithmCatalogService(AlgorithmDefinitionRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<AlgorithmDefinitionResponse> list() {
        return repository.findAllByOrderByMissionTypeAscNameAsc().stream().map(AlgorithmDefinitionResponse::from).toList();
    }

    @Transactional
    public AlgorithmDefinitionResponse setEnabled(String code, boolean enabled) {
        AlgorithmDefinition definition = find(code);
        if (!enabled && definition.isDefaultForType()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "默认算法不能直接停用，请先设置同类型的其他默认算法");
        }
        definition.setEnabled(enabled);
        return AlgorithmDefinitionResponse.from(definition);
    }

    @Transactional
    public AlgorithmDefinitionResponse setDefault(String code) {
        AlgorithmDefinition definition = find(code);
        if (!definition.isEnabled()) throw new BusinessException(ErrorCode.BAD_REQUEST, "停用算法不能设为默认算法");
        repository.findAllByMissionType(definition.getMissionType()).forEach(item -> item.setDefaultForType(item.getCode().equals(code)));
        return AlgorithmDefinitionResponse.from(definition);
    }

    @Transactional(readOnly = true)
    public AlgorithmDefinition requireEnabled(String code) {
        AlgorithmDefinition definition = find(code);
        if (!definition.isEnabled()) throw new BusinessException(ErrorCode.BAD_REQUEST, "所选算法已停用：" + code);
        return definition;
    }

    private AlgorithmDefinition find(String code) {
        return repository.findByCode(code).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "算法不存在：" + code));
    }
}
