package com.ssafy.projectree.domain.nodeCategory.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.nodeCategory.entity.Category;
import com.ssafy.projectree.domain.nodeCategory.entity.NodeCategory;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Sort;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class NodeCategoryRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private NodeCategoryRepository nodeCategoryRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("data.sql 시드로 Category enum 상수 개수만큼 카테고리가 저장되어 있다.")
    @Test
    void seedRowCount() {
        // when
        long count = nodeCategoryRepository.count();

        // then
        assertThat(count).isEqualTo(Category.values().length);
    }

    @DisplayName("data.sql 시드에 Category enum의 모든 상수가 빠짐없이 들어 있다.")
    @Test
    void seedCoversAllEnumConstants() {
        // when
        List<NodeCategory> categories = nodeCategoryRepository.findAll();

        // then
        assertThat(categories)
                .extracting(NodeCategory::getCategory)
                .containsExactlyInAnyOrder(Category.values());
    }

    @DisplayName("data.sql 시드의 id는 1부터 순서대로 매겨져 있다.")
    @Test
    void seedIdsAreSequential() {
        // when
        List<NodeCategory> categories =
                nodeCategoryRepository.findAll(Sort.by(Sort.Direction.ASC, "id"));

        // then
        assertThat(categories)
                .extracting(NodeCategory::getId)
                .containsExactly(1, 2, 3, 4, 5, 6);
    }

    @DisplayName("data.sql 시드의 id와 카테고리 짝이 정해진 값 그대로 저장되어 있다.")
    @Test
    void seedMapsIdToCategory() {
        // when
        List<NodeCategory> categories =
                nodeCategoryRepository.findAll(Sort.by(Sort.Direction.ASC, "id"));

        // then
        assertThat(categories)
                .extracting(NodeCategory::getId, NodeCategory::getCategory)
                .containsExactly(
                        tuple(1, Category.Frontend),
                        tuple(2, Category.Backend),
                        tuple(3, Category.AI),
                        tuple(4, Category.Infra),
                        tuple(5, Category.Planning),
                        tuple(6, Category.Design)
                );
    }

    @DisplayName("category 컬럼에는 ordinal이 아니라 enum 이름이 문자열로 저장된다.")
    @Test
    void categoryIsPersistedAsEnumName() {
        // when
        Object stored = entityManager
                .createNativeQuery("select category from node_category where id = 1")
                .getSingleResult();

        // then
        assertThat(stored).isEqualTo(Category.Frontend.name());
    }

    @DisplayName("data.sql에 적힌 모든 문자열이 Category enum 상수로 역매핑된다.")
    @Test
    void everySeedValueMapsBackToEnum() {
        // when
        @SuppressWarnings("unchecked")
        List<String> storedNames = entityManager
                .createNativeQuery("select category from node_category")
                .getResultList();

        // then
        assertThat(storedNames)
                .isNotEmpty()
                .allSatisfy(name -> assertThat(Category.valueOf(name)).isNotNull());
    }
}
