package com.ssafy.projectree.domain.meeting.record.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

/**
 * 회의록 도메인 오류. 상수 이름은 오류 응답의 errorCode 필드로 그대로 노출된다.
 * <ul>
 *     <li>MEETING_RECORD_CALLBACK_* 및 Command·Summary 관련 오류: Python Callback 연동 계약.
 *     Python이 재시도 여부를 판단하는 기준이므로 이름을 변경하지 않는다.</li>
 *     <li>MEETING_RECORD_NOT_FOUND: 프론트 조회 계약.</li>
 * </ul>
 * 어느 쪽이든 축약하지 않고 도메인을 포함한 이름을 사용한다.
 */
@Getter
@RequiredArgsConstructor
public enum MeetingRecordErrorCode implements ErrorCode {

    // 400
    MEETING_RECORD_CALLBACK_SCHEMA_UNSUPPORTED(
            HttpStatus.BAD_REQUEST,
            "지원하지 않는 회의록 Callback 스키마 버전입니다."
    ),
    MEETING_RECORD_CONTENT_TOO_LARGE(
            HttpStatus.BAD_REQUEST,
            "회의록 본문이 허용된 크기를 초과했습니다."
    ),

    // 401
    MEETING_RECORD_CALLBACK_UNAUTHORIZED(
            HttpStatus.UNAUTHORIZED,
            "회의록 Callback 인증에 실패했습니다."
    ),

    // 403
    MEETING_RECORD_UPDATE_FORBIDDEN(
            HttpStatus.FORBIDDEN,
            "회의록 수정 권한이 없습니다."
    ),

    // 404
    MEETING_RECORD_NOT_FOUND(
            HttpStatus.NOT_FOUND,
            "생성된 회의록을 찾을 수 없습니다."
    ),
    MEETING_RECORD_COMMAND_NOT_FOUND(
            HttpStatus.NOT_FOUND,
            "분석 요청 Command를 찾을 수 없습니다."
    ),

    // 409
    MEETING_RECORD_COMMAND_MISMATCH(
            HttpStatus.CONFLICT,
            "분석 요청 Command와 회의 정보가 일치하지 않습니다."
    ),
    MEETING_RECORD_SUMMARY_NOT_REQUESTED(
            HttpStatus.CONFLICT,
            "요약 생성을 요청하지 않은 회의입니다."
    ),
    MEETING_RECORD_SUMMARY_ALREADY_FAILED(
            HttpStatus.CONFLICT,
            "이미 실패 처리된 요약 분석입니다."
    ),
    MEETING_RECORD_ALREADY_CREATED_BY_ANOTHER_COMMAND(
            HttpStatus.CONFLICT,
            "다른 분석 요청으로 생성된 회의록이 이미 존재합니다."
    ),
    MEETING_RECORD_VERSION_CONFLICT(
            HttpStatus.CONFLICT,
            "다른 사용자가 회의록을 먼저 수정했습니다. 최신 내용을 다시 조회해주세요."
    );

    private final HttpStatus status;
    private final String message;
}
