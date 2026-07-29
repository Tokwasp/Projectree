package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.*;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "project")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Project extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @Column(nullable = false, length = 100)
    private String title;

    @Column(nullable = false, length = 200)
    private String content;

    @Column(length = 1024)
    private String photoUrl;

    @OneToMany(mappedBy = "project", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<ProjectMember> projectMembers = new ArrayList<>();

    @OneToMany(mappedBy = "project", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<ProjectCategory> projectCategories = new ArrayList<>();

    @Builder
    private Project(String title, String content, String photoUrl) {
        this.title = title;
        this.content = content;
        this.photoUrl = photoUrl;
    }

    public void addMember(ProjectMember pm) {
        this.projectMembers.add(pm);
        pm.assignProject(this);
    }

    public void addCategory(ProjectCategory pc) {
        this.projectCategories.add(pc);
        pc.assignProject(this);
    }

    public void removeMember(int memberId) {
        this.projectMembers.removeIf(pm -> pm.getMemberId() == memberId);
    }


}
