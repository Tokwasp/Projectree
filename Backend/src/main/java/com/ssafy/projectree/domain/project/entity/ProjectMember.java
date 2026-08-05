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

    public static ProjectMember createMember(int memberId, ProjectRole role) {
        return ProjectMember.builder()
                .memberId(memberId)
                .role(role)
                .build();
    }

    public void assignProject(Project project) {
        this.project = project;
    }

    public boolean hasMemberId(int memberId) {
        return this.memberId == memberId;
    }

    public boolean isOwner() {
        return this.role == ProjectRole.OWNER;
    }

    public boolean belongsTo(Project project) {
        if (this.project == null || project == null) {
            return false;
        }
        if (this.project == project) {
            return true;
        }
        return this.project.getId() > 0
                && this.project.getId() == project.getId();
    }
}
