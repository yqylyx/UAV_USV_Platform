package com.uavusv.platform.module.voiceintelligence;

import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestControllerAdvice(assignableTypes = AsrController.class)
@Order(-300)
public class AsrAdvice {
    @ExceptionHandler(AsrFailure.class)
    public ResponseEntity<Map<String, Object>> failure(AsrFailure e) {
        return AsrResponses.response(AsrResponses.error(e));
    }
}
