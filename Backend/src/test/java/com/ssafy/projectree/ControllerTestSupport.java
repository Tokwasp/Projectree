package com.ssafy.projectree;

import com.ssafy.projectree.domain.member.controller.AuthController;
import com.ssafy.projectree.domain.member.controller.MemberController;
import com.ssafy.projectree.domain.member.service.AuthService;
import com.ssafy.projectree.domain.member.service.MemberService;
import com.ssafy.projectree.domain.nodeCategory.controller.NodeCategoryController;
import com.ssafy.projectree.domain.nodeCategory.service.NodeCategoryService;
import com.ssafy.projectree.domain.project.controller.ProjectController;
import com.ssafy.projectree.domain.project.controller.InvitationController;
import com.ssafy.projectree.domain.project.controller.ProjectInvitationController;
import com.ssafy.projectree.domain.project.service.ProjectInvitationService;
import com.ssafy.projectree.domain.project.service.ProjectService;
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
        NodeCategoryController.class
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

}
