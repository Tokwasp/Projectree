package com.ssafy.projectree.domain.meetingreview.dto.response;

import lombok.Getter;

@Getter
public class MeetingRecordResponse {
    private String name;
    private int currentPageNum;
    private int totalElements;
}
