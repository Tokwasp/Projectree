package com.ssafy.projectree.domain.nodeCategory.service;

import com.ssafy.projectree.domain.nodeCategory.dto.response.NodeCategoryResponseDto;
import com.ssafy.projectree.domain.nodeCategory.entity.Category;
import com.ssafy.projectree.domain.nodeCategory.entity.NodeCategory;
import com.ssafy.projectree.domain.nodeCategory.repository.NodeCategoryRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Sort;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@ExtendWith(MockitoExtension.class)
class NodeCategoryServiceTest {

    @InjectMocks
    private NodeCategoryService nodeCategoryService;

    @Mock
    private NodeCategoryRepository nodeCategoryRepository;

    @DisplayName("조회한 카테고리의 id와 이름이 응답 DTO로 매핑된다.")
    @Test
    void getCategories() {
        // given
        given(nodeCategoryRepository.findAll(any(Sort.class)))
                .willReturn(List.of(
                        nodeCategory(1, Category.Frontend),
                        nodeCategory(2, Category.Backend)
                ));

        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getId, NodeCategoryResponseDto::getCategory)
                .containsExactly(
                        tuple(1, "Frontend"),
                        tuple(2, "Backend")
                );
    }

    @DisplayName("카테고리를 조회할 때 id 오름차순 정렬 조건으로 리포지토리를 호출한다.")
    @Test
    void getCategories_requestsAscendingIdSort() {
        // given
        given(nodeCategoryRepository.findAll(any(Sort.class))).willReturn(List.of());

        // when
        nodeCategoryService.getCategories();

        // then
        then(nodeCategoryRepository).should()
                .findAll(Sort.by(Sort.Direction.ASC, "id"));
    }

    @DisplayName("리포지토리가 돌려준 순서를 그대로 유지한다.")
    @Test
    void getCategories_preservesRepositoryOrder() {
        // given
        given(nodeCategoryRepository.findAll(any(Sort.class)))
                .willReturn(List.of(
                        nodeCategory(3, Category.AI),
                        nodeCategory(1, Category.Frontend),
                        nodeCategory(2, Category.Backend)
                ));

        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getCategory)
                .containsExactly("AI", "Frontend", "Backend");
    }

    @DisplayName("등록된 카테고리가 없으면 빈 목록을 반환한다.")
    @Test
    void getCategories_empty() {
        // given
        given(nodeCategoryRepository.findAll(any(Sort.class))).willReturn(List.of());

        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        assertThat(categories).isEmpty();
    }

    @DisplayName("Category enum의 모든 상수가 이름 그대로 응답에 담긴다.")
    @Test
    void getCategories_mapsEveryEnumConstant() {
        // given
        List<NodeCategory> stored = Arrays.stream(Category.values())
                .map(category -> nodeCategory(category.ordinal() + 1, category))
                .toList();
        given(nodeCategoryRepository.findAll(any(Sort.class))).willReturn(stored);

        // when
        List<NodeCategoryResponseDto> categories = nodeCategoryService.getCategories();

        // then
        String[] expected = Arrays.stream(Category.values())
                .map(Category::name)
                .toArray(String[]::new);
        assertThat(categories)
                .extracting(NodeCategoryResponseDto::getCategory)
                .containsExactly(expected);
    }

    private NodeCategory nodeCategory(int id, Category category) {
        NodeCategory nodeCategory = new NodeCategory();
        ReflectionTestUtils.setField(nodeCategory, "id", id);
        ReflectionTestUtils.setField(nodeCategory, "category", category);

        return nodeCategory;
    }
}
