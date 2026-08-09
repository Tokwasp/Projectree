package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectListResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.time.LocalDateTime;
import java.util.List;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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

    @DisplayName("카테고리 없이 제목과 설명만으로 프로젝트를 생성한다.")
    @Test
    void createProject_withoutCategoryIds() throws Exception {
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
                                        createRequest("포트폴리오 사이트")
                                ))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andExpect(status().isCreated());

        // then
        then(projectService).should().createProject(captor.capture(), anyInt());
        assertThat(captor.getValue())
                .extracting(ProjectCreateRequest::getTitle, ProjectCreateRequest::getContent,
                        ProjectCreateRequest::getPhotoUrl)
                .containsExactly("포트폴리오 사이트", "React로 만든 개인 포트폴리오입니다.", null);
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
        mockMvc.perform(put("/api/projects").session(loginSession(10)))
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

    @DisplayName("OWNER가 프로젝트를 삭제하면 200과 성공 메시지를 응답한다.")
    @Test
    void deleteProject() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}", 1).session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data").isEmpty());
    }

    @DisplayName("경로의 projectId와 세션의 로그인 회원 id가 서비스로 그대로 전달된다.")
    @Test
    void deleteProject_passesProjectIdAndLoginMemberId() throws Exception {
        // when
        mockMvc.perform(delete("/api/projects/{projectId}", 7).session(loginSession(10)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().deleteProject(eq(7), eq(10));
    }

    @DisplayName("세션이 아예 없으면 401을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void deleteProject_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}", 1))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));

        then(projectService).should(never()).deleteProject(anyInt(), anyInt());
    }

    @DisplayName("삭제 권한이 없으면 403과 권한 오류 메시지를 응답한다.")
    @Test
    void deleteProject_forbidden() throws Exception {
        // given
        willThrow(new CustomException(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN))
                .given(projectService).deleteProject(anyInt(), anyInt());

        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}", 1).session(loginSession(10)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_DELETE_FORBIDDEN"))
                .andExpect(jsonPath("$.errorMessage").value("프로젝트 삭제 권한이 없습니다."));
    }

    @DisplayName("존재하지 않는 프로젝트를 삭제하려 하면 404를 응답한다.")
    @Test
    void deleteProject_projectNotFound() throws Exception {
        // given
        willThrow(new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND))
                .given(projectService).deleteProject(anyInt(), anyInt());

        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}", 999).session(loginSession(10)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("존재하지 않는 프로젝트입니다."));
    }

    @DisplayName("projectId가 정수가 아니면 500이 아니라 400을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void deleteProject_withNonIntegerProjectId() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}", "abc").session(loginSession(10)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never()).deleteProject(anyInt(), anyInt());
    }

    @DisplayName("projectId 없이 삭제를 요청하면 500이 아니라 405를 응답한다.")
    @Test
    void deleteProject_withoutProjectId() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects").session(loginSession(10)))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.errorCode").value("METHOD_NOT_ALLOWED"));

        then(projectService).should(never()).deleteProject(anyInt(), anyInt());
    }

    @DisplayName("프로젝트에서 탈퇴하면 200과 성공 메시지를 응답한다.")
    @Test
    void leaveProject() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", 1)
                        .session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data").isEmpty());
    }

    @DisplayName("탈퇴 요청의 경로 projectId와 세션의 로그인 회원 id가 서비스로 그대로 전달된다.")
    @Test
    void leaveProject_passesProjectIdAndLoginMemberId() throws Exception {
        // when
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", 7)
                        .session(loginSession(10)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().leaveProject(eq(7), eq(10));
    }

    @DisplayName("세션이 아예 없으면 탈퇴 요청에 401을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void leaveProject_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", 1))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));

        then(projectService).should(never()).leaveProject(anyInt(), anyInt());
    }

    @DisplayName("OWNER가 탈퇴하려 하면 403과 탈퇴 권한 오류 메시지를 응답한다.")
    @Test
    void leaveProject_forbidden() throws Exception {
        // given
        willThrow(new CustomException(ProjectErrorCode.PROJECT_LEAVE_FORBIDDEN))
                .given(projectService).leaveProject(anyInt(), anyInt());

        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", 1)
                        .session(loginSession(10)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_LEAVE_FORBIDDEN"))
                .andExpect(jsonPath("$.errorMessage").value("프로젝트 탈퇴 권한이 없습니다."));
    }

    @DisplayName("참여하지 않은 프로젝트에서 탈퇴하려 하면 404를 응답한다.")
    @Test
    void leaveProject_participantNotFound() throws Exception {
        // given
        willThrow(new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND))
                .given(projectService).leaveProject(anyInt(), anyInt());

        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", 1)
                        .session(loginSession(10)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_PARTICIPANT_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("프로젝트에 참여 중인 회원이 아닙니다."));
    }

    @DisplayName("탈퇴 요청의 projectId가 정수가 아니면 500이 아니라 400을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void leaveProject_withNonIntegerProjectId() throws Exception {
        // when // then
        mockMvc.perform(delete("/api/projects/{projectId}/members/me", "abc")
                        .session(loginSession(10)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never()).leaveProject(anyInt(), anyInt());
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

    @DisplayName("팀원 목록을 조회하면 200과 참여자 목록을 응답한다.")
    @Test
    void getProjectMembers() throws Exception {
        // given
        given(projectService.getProjectMembers(anyInt(), anyInt()))
                .willReturn(List.of(
                        memberResponse(10, "김오너", "owner@gmail.com", ProjectRole.OWNER),
                        memberResponse(11, "이멤버", "member@gmail.com", ProjectRole.MEMBER)
                ));

        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", 1).session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.members").isArray())
                .andExpect(jsonPath("$.data.members.length()").value(2))
                .andExpect(jsonPath("$.data.members[0].memberId").value(10))
                .andExpect(jsonPath("$.data.members[0].name").value("김오너"))
                .andExpect(jsonPath("$.data.members[0].email").value("owner@gmail.com"))
                .andExpect(jsonPath("$.data.members[0].role").value("OWNER"))
                .andExpect(jsonPath("$.data.members[0].joinedAt").exists())
                .andExpect(jsonPath("$.data.members[1].memberId").value(11))
                .andExpect(jsonPath("$.data.members[1].role").value("MEMBER"));
    }

    @DisplayName("팀원 목록 응답은 배열이 아니라 members 를 가진 객체로 감싸진다.")
    @Test
    void getProjectMembers_wrapsMembersInObject() throws Exception {
        // given
        given(projectService.getProjectMembers(anyInt(), anyInt()))
                .willReturn(List.of(memberResponse(10, "김오너", "owner@gmail.com", ProjectRole.OWNER)));

        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", 1).session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").isMap())
                .andExpect(jsonPath("$.data.members").isArray());
    }

    @DisplayName("팀원 목록 조회의 경로 projectId와 세션의 로그인 회원 id가 서비스로 그대로 전달된다.")
    @Test
    void getProjectMembers_passesProjectIdAndLoginMemberId() throws Exception {
        // given
        given(projectService.getProjectMembers(anyInt(), anyInt())).willReturn(List.of());

        // when
        mockMvc.perform(get("/api/projects/{projectId}/members", 7).session(loginSession(10)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectMembers(eq(7), eq(10));
    }

    @DisplayName("세션이 아예 없으면 팀원 목록 조회에 401을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void getProjectMembers_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", 1))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));

        then(projectService).should(never()).getProjectMembers(anyInt(), anyInt());
    }

    @DisplayName("참여하지 않은 프로젝트의 팀원 목록을 조회하면 404를 응답한다.")
    @Test
    void getProjectMembers_participantNotFound() throws Exception {
        // given
        given(projectService.getProjectMembers(anyInt(), anyInt()))
                .willThrow(new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND));

        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", 1).session(loginSession(10)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_PARTICIPANT_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("프로젝트에 참여 중인 회원이 아닙니다."));
    }

    @DisplayName("존재하지 않는 프로젝트의 팀원 목록을 조회하면 404를 응답한다.")
    @Test
    void getProjectMembers_projectNotFound() throws Exception {
        // given
        given(projectService.getProjectMembers(anyInt(), anyInt()))
                .willThrow(new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));

        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", 999).session(loginSession(10)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_NOT_FOUND"))
                .andExpect(jsonPath("$.errorMessage").value("존재하지 않는 프로젝트입니다."));
    }

    @DisplayName("팀원 목록 조회의 projectId가 정수가 아니면 500이 아니라 400을 응답하고 서비스를 호출하지 않는다.")
    @Test
    void getProjectMembers_withNonIntegerProjectId() throws Exception {
        // when // then
        mockMvc.perform(get("/api/projects/{projectId}/members", "abc").session(loginSession(10)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(projectService).should(never()).getProjectMembers(anyInt(), anyInt());
    }

    @DisplayName("로그인 세션이 있으면 참여 중인 프로젝트 목록과 페이지 정보를 응답한다.")
    @Test
    void getProjectList() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(projectListResponse(
                        List.of(
                                new ProjectItemResponse(1, "포트폴리오 사이트", "https://projectree.site/1.png", 3),
                                new ProjectItemResponse(2, "스터디 관리 서비스", null, 1)
                        ),
                        PageRequest.of(0, 10),
                        2
                ));

        // when // then
        mockMvc.perform(get("/api/projects").session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.projects.length()").value(2))
                .andExpect(jsonPath("$.data.projects[0].projectId").value(1))
                .andExpect(jsonPath("$.data.projects[0].title").value("포트폴리오 사이트"))
                .andExpect(jsonPath("$.data.projects[0].photoUrl").value("https://projectree.site/1.png"))
                .andExpect(jsonPath("$.data.projects[0].memberCnt").value(3))
                .andExpect(jsonPath("$.data.projects[1].projectId").value(2))
                .andExpect(jsonPath("$.data.projects[1].photoUrl").isEmpty())
                .andExpect(jsonPath("$.data.projects[1].memberCnt").value(1))
                .andExpect(jsonPath("$.data.page").value(0))
                .andExpect(jsonPath("$.data.size").value(10))
                .andExpect(jsonPath("$.data.totalElements").value(2))
                .andExpect(jsonPath("$.data.totalPages").value(1));
    }

    @DisplayName("참여 중인 프로젝트가 없으면 빈 목록을 응답한다.")
    @Test
    void getProjectList_withNoProject() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());

        // when // then
        mockMvc.perform(get("/api/projects").session(loginSession(10)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.projects").isArray())
                .andExpect(jsonPath("$.data.projects").isEmpty())
                .andExpect(jsonPath("$.data.totalElements").value(0))
                .andExpect(jsonPath("$.data.totalPages").value(0));
    }

    @DisplayName("페이지 파라미터가 없으면 0페이지, 10개, 최신순 기본값으로 조회한다.")
    @Test
    void getProjectList_withDefaultPageable() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());
        ArgumentCaptor<Pageable> captor = ArgumentCaptor.forClass(Pageable.class);

        // when
        mockMvc.perform(get("/api/projects").session(loginSession(10)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(captor.capture(), anyInt(), any());
        Pageable pageable = captor.getValue();
        assertThat(pageable.getPageNumber()).isZero();
        assertThat(pageable.getPageSize()).isEqualTo(10);
        assertThat(pageable.getSort()).containsExactly(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        );
    }

    @DisplayName("요청한 page, size가 서비스로 그대로 전달된다.")
    @Test
    void getProjectList_passesPageable() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());
        ArgumentCaptor<Pageable> captor = ArgumentCaptor.forClass(Pageable.class);

        // when
        mockMvc.perform(
                        get("/api/projects")
                                .session(loginSession(10))
                                .param("page", "2")
                                .param("size", "5")
                )
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(captor.capture(), anyInt(), any());
        assertThat(captor.getValue().getPageNumber()).isEqualTo(2);
        assertThat(captor.getValue().getPageSize()).isEqualTo(5);
    }

    @DisplayName("size가 상한을 넘으면 50으로 제한된다.")
    @Test
    void getProjectList_withTooLargeSize() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());
        ArgumentCaptor<Pageable> captor = ArgumentCaptor.forClass(Pageable.class);

        // when
        mockMvc.perform(
                        get("/api/projects")
                                .session(loginSession(10))
                                .param("size", "1000")
                )
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(captor.capture(), anyInt(), any());
        assertThat(captor.getValue().getPageSize()).isEqualTo(50);
    }

    @DisplayName("프로젝트 목록 조회 시 세션의 로그인 회원 id가 서비스로 그대로 전달된다.")
    @Test
    void getProjectList_passesLoginMemberId() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());

        // when
        mockMvc.perform(get("/api/projects").session(loginSession(42)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(any(Pageable.class), eq(42), any());
    }

    @DisplayName("keyword 파라미터를 붙여서 조회하면 서비스로 그대로 전달된다.")
    @Test
    void getProjectList_passesKeyword() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());

        // when
        mockMvc.perform(
                        get("/api/projects")
                                .session(loginSession(10))
                                .param("keyword", "포트폴리오")
                )
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(any(Pageable.class), anyInt(), eq("포트폴리오"));
    }

    @DisplayName("keyword 파라미터가 없으면 서비스에 null이 전달된다.")
    @Test
    void getProjectList_withoutKeyword() throws Exception {
        // given
        given(projectService.getProjectList(any(Pageable.class), anyInt(), any()))
                .willReturn(emptyProjectListResponse());

        // when
        mockMvc.perform(get("/api/projects").session(loginSession(10)))
                .andExpect(status().isOk());

        // then
        then(projectService).should().getProjectList(any(Pageable.class), anyInt(), isNull());
    }

    @DisplayName("세션이 없으면 프로젝트 목록을 조회할 수 없다.")
    @Test
    void getProjectList_withoutSession() throws Exception {
        // when // then
        mockMvc.perform(get("/api/projects"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.errorMessage").value("로그인이 필요합니다."));

        then(projectService).should(never()).getProjectList(any(Pageable.class), anyInt(), any());
    }

    private ProjectListResponse emptyProjectListResponse() {
        return projectListResponse(List.of(), PageRequest.of(0, 10), 0);
    }

    private ProjectListResponse projectListResponse(List<ProjectItemResponse> items, Pageable pageable, long total) {
        return new ProjectListResponse(new PageImpl<>(items, pageable, total));
    }

    private ProjectMemberResponse memberResponse(int memberId, String name, String email, ProjectRole role) {
        return new ProjectMemberResponse(memberId, name, email, role, LocalDateTime.of(2026, 7, 31, 1, 0));
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
        return ProjectCreateRequest.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
    }
}
