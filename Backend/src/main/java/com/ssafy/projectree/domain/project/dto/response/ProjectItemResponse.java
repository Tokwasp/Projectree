package com.ssafy.projectree.domain.project.dto.response;

import lombok.Getter;

@Getter
public class ProjectItemResponse {

    private final int projectId;
    private final String title;
    private final String photoUrl;
    private final long memberCnt;

    public ProjectItemResponse(int projectId, String title, String photoUrl, long memberCnt) {
        this.projectId = projectId;
        this.title = title;
        this.photoUrl = photoUrl;
        this.memberCnt = memberCnt;
    }
}
