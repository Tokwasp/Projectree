package com.ssafy.projectree;

import com.ssafy.projectree.domain.member.controller.AuthController;
import com.ssafy.projectree.domain.member.controller.MemberController;
import com.ssafy.projectree.domain.member.service.AuthService;
import com.ssafy.projectree.domain.member.service.MemberService;
import com.ssafy.projectree.domain.meeting.controller.MeetingController;
import com.ssafy.projectree.domain.meeting.record.controller.MeetingRecordController;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordQueryService;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordUpdateService;
import com.ssafy.projectree.domain.meeting.result.graph.query.GraphQueryController;
import com.ssafy.projectree.domain.meeting.result.graph.query.GraphQueryService;
import com.ssafy.projectree.domain.meeting.result.graph.command.GraphNodeCommandController;
import com.ssafy.projectree.domain.meeting.result.graph.command.GraphNodeUpdateService;
import com.ssafy.projectree.domain.meeting.result.graph.delete.GraphNodeDeleteService;
import com.ssafy.projectree.domain.meeting.result.graph.delete.GraphNodeDeleteStatusService;
import com.ssafy.projectree.domain.meeting.service.MeetingAnalysisRequestService;
import com.ssafy.projectree.domain.nodeCategory.controller.NodeCategoryController;
import com.ssafy.projectree.domain.nodeCategory.service.NodeCategoryService;
import com.ssafy.projectree.domain.notification.controller.NotificationController;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import com.ssafy.projectree.domain.project.controller.ProjectController;
import com.ssafy.projectree.domain.project.controller.InvitationController;
import com.ssafy.projectree.domain.project.controller.ProjectInvitationController;
import com.ssafy.projectree.domain.project.service.ProjectInvitationService;
import com.ssafy.projectree.domain.project.service.ProjectService;
import com.ssafy.projectree.global.s3.S3Controller;
import com.ssafy.projectree.global.s3.S3Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;

@WebMvcTest(controllers = {
        AuthController.class,
        MemberController.class,
        ProjectController.class,
        ProjectInvitationController.class,
        InvitationController.class,
        NodeCategoryController.class,
        MeetingController.class,
        MeetingRecordController.class,
        GraphQueryController.class,
        GraphNodeCommandController.class,
        NotificationController.class,
        S3Controller.class
})
public abstract class ControllerTestSupport {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected ObjectMapper objectMapper;

    @MockitoBean
    protected AuthService authService;

    @MockitoBean
    protected MemberService memberService;

    @MockitoBean
    protected ProjectService projectService;

    @MockitoBean
    protected ProjectInvitationService projectInvitationService;

    @MockitoBean
    protected NodeCategoryService nodeCategoryService;

    @MockitoBean
    protected MeetingAnalysisRequestService meetingAnalysisRequestService;

    @MockitoBean
    protected MeetingRecordQueryService meetingRecordQueryService;

    @MockitoBean
    protected MeetingRecordUpdateService meetingRecordUpdateService;

    @MockitoBean
    protected GraphQueryService graphQueryService;

    @MockitoBean
    protected GraphNodeUpdateService graphNodeUpdateService;

    @MockitoBean
    protected GraphNodeDeleteService graphNodeDeleteService;

    @MockitoBean
    protected GraphNodeDeleteStatusService graphNodeDeleteStatusService;

    @MockitoBean
    protected NotificationService notificationService;

    @MockitoBean
    protected S3Service s3Service;

}
