package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class ProjectMemberRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("프로젝트 참여자를 회원 정보와 함께 조회한다.")
    @Test
    void findMemberResponsesByProjectId() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result).hasSize(1);
        assertThat(result.getFirst())
                .extracting("memberId", "name", "email", "role")
                .containsExactly(owner.getId(), "김오너", "owner@gmail.com", ProjectRole.OWNER);
    }

    @DisplayName("memberId 에는 project_member 의 id 가 아니라 회원의 id 가 담긴다.")
    @Test
    void findMemberResponsesByProjectId_mapsMemberIdNotProjectMemberId() {
        // given
        // 회원을 여러 명 저장해 회원 id 와 project_member id 가 어긋나게 만든다
        memberRepository.save(createMember("dummy1@gmail.com", "더미1"));
        memberRepository.save(createMember("dummy2@gmail.com", "더미2"));
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));

        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result.getFirst().getMemberId()).isEqualTo(owner.getId());
    }

    @DisplayName("나중에 참여했더라도 OWNER 가 목록의 맨 앞에 온다.")
    @Test
    void findMemberResponsesByProjectId_ordersOwnerFirst() {
        // given
        Member normal = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));

        // MEMBER 를 먼저 넣어 정렬이 실제로 동작하는지 확인한다
        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(normal.getId(), ProjectRole.MEMBER),
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result)
                .extracting("name", "role")
                .containsExactly(
                        tuple("김오너", ProjectRole.OWNER),
                        tuple("이멤버", ProjectRole.MEMBER)
                );
    }

    @DisplayName("같은 role 안에서는 참여한 순서대로 정렬된다.")
    @Test
    void findMemberResponsesByProjectId_ordersByJoinOrderWithinSameRole() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member first = memberRepository.save(createMember("first@gmail.com", "먼저온사람"));
        Member second = memberRepository.save(createMember("second@gmail.com", "나중에온사람"));

        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER),
                ProjectMember.createMember(first.getId(), ProjectRole.MEMBER),
                ProjectMember.createMember(second.getId(), ProjectRole.MEMBER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너", "먼저온사람", "나중에온사람");
    }

    @DisplayName("다른 프로젝트의 참여자는 목록에 포함되지 않는다.")
    @Test
    void findMemberResponsesByProjectId_excludesOtherProjectMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남의프로젝트사람"));

        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        saveProject("스터디 관리 앱",
                ProjectMember.createMember(outsider.getId(), ProjectRole.OWNER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    @DisplayName("회원 행이 없는 memberId 는 목록에서 제외된다.")
    @Test
    void findMemberResponsesByProjectId_excludesDanglingMemberId() {
        // given
        // project_member.member_id 에는 FK 제약이 없어 존재하지 않는 회원을 가리킬 수 있다.
        // inner join 이므로 그런 행은 목록에서 조용히 빠진다.
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int notExistingMemberId = 999_999;

        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER),
                ProjectMember.createMember(notExistingMemberId, ProjectRole.MEMBER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    @DisplayName("참여일이 채워진 채로 조회된다.")
    @Test
    void findMemberResponsesByProjectId_populatesJoinedAt() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int projectId = saveProject("포트폴리오 사이트",
                ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(projectId);

        // then
        assertThat(result.getFirst().getJoinedAt()).isNotNull();
    }

    @DisplayName("존재하지 않는 프로젝트를 조회하면 빈 목록을 반환한다.")
    @Test
    void findMemberResponsesByProjectId_withNotExistingProject() {
        // when
        List<ProjectMemberResponse> result =
                projectMemberRepository.findMemberResponsesByProjectId(999_999);

        // then
        assertThat(result).isEmpty();
    }

    private int saveProject(String title, ProjectMember... members) {
        Project project = Project.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();

        for (ProjectMember member : members) {
            project.addMember(member);
        }

        return projectRepository.save(project).getId();
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

    private void flushAndClear() {
        entityManager.flush();
        entityManager.clear();
    }
}
