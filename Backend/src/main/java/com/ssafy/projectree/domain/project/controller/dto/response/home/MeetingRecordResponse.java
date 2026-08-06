package com.ssafy.projectree.domain.project.controller.dto.response.home;

import lombok.Getter;

@Getter
public class MeetingRecordResponse {
    private String name;
    private int currentPageNum;
    private int totalElements;
}
