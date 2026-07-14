package com.uavusv.platform.common.exception;

import org.springframework.http.HttpStatus;

public enum ErrorCode {
    BAD_REQUEST("COMMON_400", "请求参数不正确", HttpStatus.BAD_REQUEST),
    UNAUTHORIZED("AUTH_401", "用户名或密码错误", HttpStatus.UNAUTHORIZED),
    CSRF_INVALID("AUTH_403_CSRF", "安全令牌已失效，请刷新页面后重试", HttpStatus.FORBIDDEN),
    FORBIDDEN("AUTH_403", "没有权限执行此操作", HttpStatus.FORBIDDEN),
    NOT_FOUND("COMMON_404", "请求的资源不存在", HttpStatus.NOT_FOUND),
    DEVICE_NOT_FOUND("DEVICE_404", "设备不存在", HttpStatus.NOT_FOUND),
    DEVICE_CODE_EXISTS("DEVICE_409", "设备编码已存在", HttpStatus.CONFLICT),
    INTERNAL_SERVER_ERROR("COMMON_500", "服务器内部错误", HttpStatus.INTERNAL_SERVER_ERROR);

    private final String code;
    private final String message;
    private final HttpStatus httpStatus;

    ErrorCode(String code, String message, HttpStatus httpStatus) {
        this.code = code;
        this.message = message;
        this.httpStatus = httpStatus;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }

    public HttpStatus getHttpStatus() {
        return httpStatus;
    }
}
