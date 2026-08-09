package com.ssafy.projectree.global.s3;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.s3.dto.response.PresignedUrlResponse;
import com.ssafy.projectree.global.s3.exception.S3ErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class S3ControllerTest extends ControllerTestSupport {

    @DisplayName("로그인 세션과 업로드 타입을 함께 보내면 200을 응답한다.")
    @Test
    void getPresignedUrl() throws Exception {
        // given
        given(s3Service.generatePresignedUrl(UploadType.PROFILE)).willReturn(presignedUrlResponse());

        // when // then
        mockMvc.perform(get("/api/s3/presigned-url")
                        .session(loginSession(10))
                        .param("type", "PROFILE"))
                .andExpect(status().isOk());
    }

    @DisplayName("로그인 세션이 없으면 401을 응답한다.")
    @Test
    void getPresignedUrl_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(get("/api/s3/presigned-url")
                        .param("type", "PROFILE"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));

        then(s3Service).should(never()).generatePresignedUrl(any(UploadType.class));
    }

    @DisplayName("정의되지 않은 업로드 타입을 보내면 400을 응답한다.")
    @Test
    void getPresignedUrl_withUnknownType() throws Exception {
        // when // then
        mockMvc.perform(get("/api/s3/presigned-url")
                        .session(loginSession(10))
                        .param("type", "UNKNOWN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(s3Service).should(never()).generatePresignedUrl(any(UploadType.class));
    }

    @DisplayName("업로드 타입을 보내지 않으면 400을 응답한다.")
    @Test
    void getPresignedUrl_withoutType() throws Exception {
        // when // then
        mockMvc.perform(get("/api/s3/presigned-url")
                        .session(loginSession(10)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(s3Service).should(never()).generatePresignedUrl(any(UploadType.class));
    }

    @DisplayName("POST로 요청하면 405를 응답한다.")
    @Test
    void getPresignedUrl_withNotAllowedMethod() throws Exception {
        // when // then
        mockMvc.perform(post("/api/s3/presigned-url"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.errorCode").value("METHOD_NOT_ALLOWED"));
    }

    @DisplayName("URL 발급이 실패하면 PRESIGNED_URL_FAILED로 500을 응답한다.")
    @Test
    void getPresignedUrl_whenIssuingFails() throws Exception {
        // given
        given(s3Service.generatePresignedUrl(any(UploadType.class)))
                .willThrow(new CustomException(S3ErrorCode.PRESIGNED_URL_FAILED));

        // when // then
        mockMvc.perform(get("/api/s3/presigned-url")
                        .session(loginSession(10))
                        .param("type", "PROFILE"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.errorCode").value("PRESIGNED_URL_FAILED"));
    }

    private PresignedUrlResponse presignedUrlResponse() {
        return PresignedUrlResponse.of(
                "https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/profile/2026_08_03/uuid?X-Amz-Signature=abc",
                "https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/profile/2026_08_03/uuid"
        );
    }

    private MockHttpSession loginSession(int memberId) {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(memberId)
                .name("김싸피")
                .email("ssafy@gmail.com")
                .build());

        return session;
    }
}
