package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.databind.node.ObjectNode;

import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice(assignableTypes = VoiceController.class)
@Order(-200)
public class VoiceMvcErrors {
    private final VoiceExceptionHandler errors;

    public VoiceMvcErrors(VoiceExceptionHandler errors) {
        this.errors = errors;
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MissingRequestHeaderException.class})
    public ResponseEntity<ObjectNode> invalid(Exception e) {
        return errors.failure(VoiceFailure.bad());
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ObjectNode> media(Exception e) {
        return errors.failure(new VoiceFailure(415, "UNSUPPORTED_MEDIA_TYPE"));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ObjectNode> denied(Exception e) {
        return errors.failure(new VoiceFailure(403, "FORBIDDEN"));
    }
}
