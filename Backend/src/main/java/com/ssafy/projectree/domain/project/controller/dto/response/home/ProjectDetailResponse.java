package com.ssafy.projectree.domain.project.controller.dto.response.home;

import com.ssafy.projectree.domain.project.entity.Project;
import lombok.Builder;
import lombok.Getter;

@Getter
public class ProjectDetailResponse {
    private String projectTitle;
    private String projectContent;
    private int participantCount;

    @Builder
    private ProjectDetailResponse(String projectTitle, String projectContent, int participantCount) {
        this.projectTitle = projectTitle;
        this.projectContent = projectContent;
        this.participantCount = participantCount;
    }

    public static ProjectDetailResponse of(Project project){
        return ProjectDetailResponse.builder()
                .projectTitle(project.getTitle())
                .projectContent(project.getContent())
                .participantCount(project.getProjectMembers().size())
                .build();
    }
}
