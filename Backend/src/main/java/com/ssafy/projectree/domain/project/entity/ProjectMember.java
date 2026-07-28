package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(
        name = "project_member",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_project_member",
                columnNames = {"project_id", "member_id"}
        )
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ProjectMember extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    // member는 다른 도메인이므로 엔티티가 아닌 id로 참조한다.
    @Column(name = "member_id", nullable = false)
    private Integer memberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProjectRole role;

    @Builder
    private ProjectMember(Project project, Integer memberId, ProjectRole role) {
        this.project = project;
        this.memberId = memberId;
        this.role = role;
    }

    // 프로젝트 role 변경 메서드
    public void changeRole(ProjectRole role) {
        this.role = role;
    }
}
