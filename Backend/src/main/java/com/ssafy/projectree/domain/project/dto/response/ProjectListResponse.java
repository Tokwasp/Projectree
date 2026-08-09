package com.ssafy.projectree.domain.project.dto.response;

import lombok.Getter;
import org.springframework.data.domain.Page;

import java.util.List;

@Getter
public class ProjectListResponse {

    private final List<ProjectItemResponse> projects;
    private final int page;
    private final int size;
    private final long totalElements;
    private final int totalPages;

    public ProjectListResponse(Page<ProjectItemResponse> pages){
        this.projects=pages.getContent();
        this.page=pages.getNumber();
        this.size=pages.getSize();
        this.totalElements=pages.getTotalElements();
        this.totalPages=pages.getTotalPages();
    }
}
