package com.ssafy.projectree.domain.nodeCategory.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.nodeCategory.dto.response.NodeCategoryResponseDto;
import com.ssafy.projectree.domain.nodeCategory.entity.Category;
import com.ssafy.projectree.domain.nodeCategory.entity.NodeCategory;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class NodeCategoryControllerTest extends ControllerTestSupport {

    @DisplayName("카테고리 조회는 로그인 세션이 없어도 가능하다.")
    @Test
    void getCategories_withoutSession() throws Exception {
        // given
        given(nodeCategoryService.getCategories())
                .willReturn(List.of(response(1, Category.Frontend)));

        // when // then
        mockMvc.perform(get("/api/categories"))
                .andExpect(status().isOk());
    }

    @DisplayName("매핑되지 않은 HTTP 메서드로 요청하면 405를 응답한다.")
    @Test
    void getCategories_withNotAllowedMethod() throws Exception {
        // when // then
        mockMvc.perform(post("/api/categories"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.status").value(405))
                .andExpect(jsonPath("$.errorCode").value("METHOD_NOT_ALLOWED"));
    }

    @DisplayName("서비스에서 예기치 못한 예외가 발생하면 500과 INTERNAL_SERVER_ERROR를 응답한다.")
    @Test
    void getCategories_serviceThrows() throws Exception {
        // given
        given(nodeCategoryService.getCategories())
                .willThrow(new RuntimeException("의도적으로 발생시킨 예외"));

        // when // then
        mockMvc.perform(get("/api/categories"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.errorCode").value("INTERNAL_SERVER_ERROR"));
    }

    private NodeCategoryResponseDto response(int id, Category category) {
        NodeCategory nodeCategory = new NodeCategory();
        ReflectionTestUtils.setField(nodeCategory, "id", id);
        ReflectionTestUtils.setField(nodeCategory, "category", category);

        return new NodeCategoryResponseDto(nodeCategory);
    }
}
