package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.util.Arrays;
import java.util.List;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ProjectControllerTest extends ControllerTestSupport {

    @DisplayName("로그인 세션이 있으면 프로젝트를 생성하고 201과 생성된 프로젝트 id를 응답한다.")
    @Test
    void createProject() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willReturn(1);

        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data").value(1));
    }

    @DisplayName("세션의 로그인 회원 id가 서비스로 그대로 전달된다.")
    @Test
    void createProject_passesLoginMemberId() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willReturn(1);

        // when
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isCreated());

        // then
        then(projectService).should()
                .createProject(any(ProjectCreateRequest.class), org.mockito.ArgumentMatchers.eq(10));
    }

    @DisplayName("세션이 아예 없으면 401을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void createProject_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("세션은 있지만 로그인 회원 정보가 담겨 있지 않으면 401을 응답한다.")
    @Test
    void createProject_withoutLoginMemberInSession() throws Exception {
        // given
        MockHttpSession emptySession = new MockHttpSession();

        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(emptySession)
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("존재하지 않는 회원이 프로젝트를 생성하려 하면 404를 응답한다.")
    @Test
    void createProject_memberNotFound() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willThrow(new CustomException(ProjectErrorCode.MEMBER_NOT_FOUND));

        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(999))
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("MEMBER_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("존재하지 않는 회원입니다."));
    }

    @DisplayName("프로젝트 제목은 필수값이다.")
    @Test
    void createProject_withoutTitle() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        ProjectCreateRequest.builder()
                                                .content("React로 만든 개인 포트폴리오입니다.")
                                                .categoryIds(List.of(1))
                                                .build()
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("프로젝트 제목은 공백일 수 없다.")
    @Test
    void createProject_withBlankTitle() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(createRequest("   ")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("프로젝트 설명은 필수값이다.")
    @Test
    void createProject_withoutContent() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        ProjectCreateRequest.builder()
                                                .title("포트폴리오 사이트")
                                                .categoryIds(List.of(1))
                                                .build()
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("프로젝트 제목은 100자를 넘을 수 없다.")
    @Test
    void createProject_withTooLongTitle() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(createRequest("가".repeat(101))))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("프로젝트 설명은 200자를 넘을 수 없다.")
    @Test
    void createProject_withTooLongContent() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        ProjectCreateRequest.builder()
                                                .title("포트폴리오 사이트")
                                                .content("가".repeat(201))
                                                .categoryIds(List.of(1))
                                                .build()
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("photoUrl은 없어도 프로젝트를 생성할 수 있다.")
    @Test
    void createProject_withoutPhotoUrl() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willReturn(1);

        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(createRequest("포트폴리오 사이트")))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data").value(1));
    }

    @DisplayName("카테고리는 필수값이다.")
    @Test
    void createProject_withoutCategoryIds() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        ProjectCreateRequest.builder()
                                                .title("포트폴리오 사이트")
                                                .content("React로 만든 개인 포트폴리오입니다.")
                                                .build()
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("카테고리를 빈 배열로 보내면 400을 응답한다.")
    @Test
    void createProject_withEmptyCategoryIds() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        createRequest("포트폴리오 사이트", List.of())
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("카테고리 배열에 null이 섞여 있으면 500이 아니라 400을 응답한다.")
    @Test
    void createProject_withNullInCategoryIds() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        createRequest("포트폴리오 사이트", Arrays.asList(1, null))
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("카테고리 id가 정수가 아니면 400을 응답한다.")
    @Test
    void createProject_withNonIntegerCategoryId() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content("""
                                        {
                                          "title": "포트폴리오 사이트",
                                          "content": "React로 만든 개인 포트폴리오입니다.",
                                          "categoryIds": ["프론트엔드"]
                                        }
                                        """)
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never())
                .createProject(any(ProjectCreateRequest.class), anyInt());
    }

    @DisplayName("유효하지 않은 카테고리 id로 프로젝트를 생성하려 하면 400과 카테고리 오류 메시지를 응답한다.")
    @Test
    void createProject_invalidCategory() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willThrow(new CustomException(ProjectErrorCode.INVALID_REQUEST));

        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        createRequest("포트폴리오 사이트", List.of(99))
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.errorMessage").value("유효하지 않은 카테고리입니다."));
    }

    @DisplayName("요청 본문의 카테고리 목록이 서비스로 그대로 전달된다.")
    @Test
    void createProject_passesCategoryIds() throws Exception {
        // given
        given(projectService.createProject(any(ProjectCreateRequest.class), anyInt()))
                .willReturn(1);
        ArgumentCaptor<ProjectCreateRequest> captor =
                ArgumentCaptor.forClass(ProjectCreateRequest.class);

        // when
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content(objectMapper.writeValueAsString(
                                        createRequest("포트폴리오 사이트", List.of(2, 4))
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isCreated());

        // then
        then(projectService).should().createProject(captor.capture(), anyInt());
        assertThat(captor.getValue().getCategoryIds()).containsExactly(2, 4);
    }

    @DisplayName("본문이 JSON으로 파싱되지 않으면 400을 응답한다.")
    @Test
    void createProject_withMalformedBody() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .content("{\"title\":")
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("매핑되지 않은 HTTP 메서드로 요청하면 500이 아니라 405를 응답한다.")
    @Test
    void createProject_withNotAllowedMethod() throws Exception {
        // when // then
        mockMvc.perform(get("/api/projects").session(loginSession(10)))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.status").value(405))
                .andExpect(jsonPath("$.errorCode").value("METHOD_NOT_ALLOWED"))
                .andExpect(jsonPath("$.errorMessage").value("지원하지 않는 HTTP 메서드입니다."));
    }

    @DisplayName("지원하지 않는 Content-Type으로 요청하면 500이 아니라 415를 응답한다.")
    @Test
    void createProject_withUnsupportedMediaType() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/projects")
                                .session(loginSession(10))
                                .contentType(MediaType.TEXT_PLAIN)
                                .content("plain text")
                )
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.status").value(415))
                .andExpect(jsonPath("$.errorCode").value("UNSUPPORTED_MEDIA_TYPE"));
    }

    @DisplayName("존재하지 않는 경로로 요청하면 500이 아니라 404를 응답한다.")
    @Test
    void requestToUnknownEndpoint() throws Exception {
        // when // then
        mockMvc.perform(get("/api/no-such-endpoint"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("ENDPOINT_NOT_FOUND"));
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

    private ProjectCreateRequest createRequest(String title) {
        return createRequest(title, List.of(1));
    }

    private ProjectCreateRequest createRequest(String title, List<Integer> categoryIds) {
        return ProjectCreateRequest.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .categoryIds(categoryIds)
                .build();
    }
}
