package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class ProjectRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private ProjectRepository projectRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("참여 중인 프로젝트만 멤버 수와 함께 조회한다.")
    @Test
    void findProjectItemsByMemberId() {
        // given
        saveProject("참여 프로젝트", 1, 2, 3);
        saveProject("미참여 프로젝트", 2, 3);
        saveProject("혼자 하는 프로젝트", 1);
        flushAndClear();

        // when
        Page<ProjectItemResponse> page = projectRepository.findProjectItemsByMemberId(
                1, PageRequest.of(0, 10, Sort.by(Sort.Direction.ASC, "id"))
        );

        // then
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getContent())
                .extracting(ProjectItemResponse::getTitle, ProjectItemResponse::getMemberCnt)
                .containsExactly(
                        tuple("참여 프로젝트", 3L),
                        tuple("혼자 하는 프로젝트", 1L)
                );
    }

    @DisplayName("createdAt, id 내림차순 정렬이 적용된다.")
    @Test
    void findProjectItemsByMemberId_withDefaultSort() {
        // given
        saveProject("첫 번째", 1);
        saveProject("두 번째", 1);
        saveProject("세 번째", 1);
        flushAndClear();

        // when
        Page<ProjectItemResponse> page = projectRepository.findProjectItemsByMemberId(
                1, PageRequest.of(0, 10, Sort.by(Sort.Direction.DESC, "createdAt", "id"))
        );

        // then
        assertThat(page.getContent())
                .extracting(ProjectItemResponse::getTitle)
                .containsExactly("세 번째", "두 번째", "첫 번째");
    }

    @DisplayName("페이지 크기만큼 나눠서 조회한다.")
    @Test
    void findProjectItemsByMemberId_withPaging() {
        // given
        saveProject("첫 번째", 1);
        saveProject("두 번째", 1);
        saveProject("세 번째", 1);
        flushAndClear();

        // when
        Page<ProjectItemResponse> secondPage = projectRepository.findProjectItemsByMemberId(
                1, PageRequest.of(1, 2, Sort.by(Sort.Direction.ASC, "id"))
        );

        // then
        assertThat(secondPage.getTotalElements()).isEqualTo(3);
        assertThat(secondPage.getTotalPages()).isEqualTo(2);
        assertThat(secondPage.getContent())
                .extracting(ProjectItemResponse::getTitle)
                .containsExactly("세 번째");
    }

    @DisplayName("프로젝트 수와 무관하게 목록 쿼리와 count 쿼리만 실행된다.")
    @Test
    void findProjectItemsByMemberId_doesNotTriggerNPlusOne() {
        // given
        saveProject("첫 번째", 1, 2);
        saveProject("두 번째", 1, 2, 3);
        saveProject("세 번째", 1, 4);
        flushAndClear();

        Statistics statistics = entityManager.getEntityManagerFactory()
                .unwrap(SessionFactory.class)
                .getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        // when
        projectRepository.findProjectItemsByMemberId(
                1, PageRequest.of(0, 2, Sort.by(Sort.Direction.ASC, "id"))
        );

        // then
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(2);
    }

    private int saveProject(String title, int... memberIds) {
        Project project = Project.builder()
                .title(title)
                .content("프로젝트 Repository 테스트입니다.")
                .build();

        for (int i = 0; i < memberIds.length; i++) {
            ProjectRole role = (i == 0) ? ProjectRole.OWNER : ProjectRole.MEMBER;
            project.addMember(ProjectMember.createMember(memberIds[i], role));
        }

        return projectRepository.save(project).getId();
    }

    private void flushAndClear() {
        entityManager.flush();
        entityManager.clear();
    }
}
