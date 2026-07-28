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
    private int id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    // member는 다른 도메인이므로 엔티티가 아닌 id로 참조한다.
    @Column(name = "member_id", nullable = false)
    private int memberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProjectRole role;

    @Builder
    private ProjectMember(int memberId, ProjectRole role) {
        this.memberId = memberId;
        this.role = role;
    }

    // 빌더에서 project 제거하면서 다른 프로젝트 넣는 상황 방지
    void assignProject(Project project) {
        this.project = project;
    }

}
