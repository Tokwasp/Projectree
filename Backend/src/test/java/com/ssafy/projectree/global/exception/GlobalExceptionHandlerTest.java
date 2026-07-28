package com.ssafy.projectree.global.exception;

import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import jakarta.validation.Valid;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GlobalExceptionHandlerTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new ProbeController())
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @DisplayName("로그인이 필요한 요청에서 BusinessException(UNAUTHORIZED)이 발생하면 401과 에러 코드를 응답한다.")
    @Test
    void handleBusinessException_unauthorized() throws Exception {
        mockMvc.perform(get("/probe/unauthorized"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));
    }

    @DisplayName("BusinessException(MEMBER_NOT_FOUND)이 발생하면 404와 에러 코드를 응답한다.")
    @Test
    void handleBusinessException_memberNotFound() throws Exception {
        mockMvc.perform(get("/probe/member-not-found"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("MEMBER_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("존재하지 않는 회원입니다."));
    }

    @DisplayName("@Valid 검증에 실패하면 400과 INVALID_REQUEST를 응답한다.")
    @Test
    void handleMethodArgumentNotValid() throws Exception {
        mockMvc.perform(
                        post("/probe/validated")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":\"  \",\"content\":\"설명입니다.\"}")
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.errorMessage").value("요청 값이 올바르지 않습니다."));
    }

    @DisplayName("본문이 JSON으로 파싱되지 않으면 400과 INVALID_REQUEST를 응답한다.")
    @Test
    void handleHttpMessageNotReadable() throws Exception {
        mockMvc.perform(
                        post("/probe/validated")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"title\":")
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("분류되지 않은 예외는 500과 INTERNAL_SERVER_ERROR를 응답한다.")
    @Test
    void handleException() throws Exception {
        mockMvc.perform(get("/probe/boom"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.errorCode").value("INTERNAL_SERVER_ERROR"))
                .andExpect(jsonPath("$.errorMessage").value("서버 내부 오류가 발생했습니다."));
    }

    @RestController
    static class ProbeController {

        @GetMapping("/probe/unauthorized")
        void unauthorized() {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }

        @GetMapping("/probe/member-not-found")
        void memberNotFound() {
            throw new BusinessException(ErrorCode.MEMBER_NOT_FOUND);
        }

        @PostMapping("/probe/validated")
        void validated(@Valid @RequestBody ProjectCreateRequest request) {
        }

        @GetMapping("/probe/boom")
        void boom() {
            throw new RuntimeException("의도적으로 발생시킨 예외");
        }
    }
}
