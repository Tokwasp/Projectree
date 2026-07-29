package com.ssafy.projectree.domain.nodeCategory.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.nodeCategory.dto.response.NodeCategoryResponseDto;
import com.ssafy.projectree.domain.nodeCategory.entity.Category;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class NodeCategoryServiceTest extends IntegrationTestSupport {

    @Autowired
    private NodeCategoryService nodeCategoryService;

    @DisplayName("등록된 카테고리를 모두 조회한다.")
    @Test
    void getCategories() {
        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories).hasSize(Category.values().length);
    }

    @DisplayName("조회 결과에 Category enum의 모든 이름이 담긴다.")
    @Test
    void getCategories_containsAllEnumNames() {
        // given
        String[] expected = Arrays.stream(Category.values())
                .map(Category::name)
                .toArray(String[]::new);

        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getName)
                .containsExactlyInAnyOrder(expected);
    }

    @DisplayName("조회 결과는 id 오름차순으로 정렬된다.")
    @Test
    void getCategories_sortedById() {
        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getId)
                .isSorted();
    }

    @DisplayName("id와 이름이 data.sql 시드 값 그대로 매핑된다.")
    @Test
    void getCategories_mapsIdAndName() {
        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getId, NodeCategoryResponseDto::getName)
                .containsExactly(
                        tuple(1, "Frontend"),
                        tuple(2, "Backend"),
                        tuple(3, "AI"),
                        tuple(4, "Infra"),
                        tuple(5, "Planning"),
                        tuple(6, "Design")
                );
    }

    @DisplayName("조회 결과에 id가 0인 항목은 없다.")
    @Test
    void getCategories_hasNoUnmappedId() {
        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getId)
                .allMatch(id -> id > 0);
    }
}
