package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "project_category",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_project_category",
                columnNames = {"project_id", "category_id"}
        ))
@NoArgsConstructor
@Getter
public class ProjectCategory extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(name = "category_id", nullable = false)
    private int categoryId;

    @Builder
    private ProjectCategory(int categoryId) {
        this.categoryId = categoryId;
    }

    public static ProjectCategory createProjectCategory(int categoryId) {
        return ProjectCategory.builder()
                .categoryId(categoryId)
                .build();
    }

    public void assignProject(Project project) {
        this.project = project;
    }


}
