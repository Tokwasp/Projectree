package com.ssafy.projectree.domain.project.controller.dto.response.home;

import lombok.Builder;
import lombok.Getter;

import java.util.List;

@Getter
public class ProjectHomeResponse {

    private ProjectDetailResponse projectDetail;
    private List<MeetingRecordResponse> meetingRecordList;
    private List<PersonalSpeakingResponse> personalSpeakingList;
    private MyMeetingReviewResponse myReview;

    @Builder
    private ProjectHomeResponse(ProjectDetailResponse projectDetail,
                                List<MeetingRecordResponse> meetingRecordList,
                                List<PersonalSpeakingResponse> personalSpeakingList,
                                MyMeetingReviewResponse myReview) {
        this.projectDetail = projectDetail;
        this.meetingRecordList = meetingRecordList;
        this.personalSpeakingList = personalSpeakingList;
        this.myReview = myReview;
    }

    public static ProjectHomeResponse of(ProjectDetailResponse projectDetail,
                                         List<MeetingRecordResponse> meetingRecordList,
                                         List<PersonalSpeakingResponse> personalSpeakingList,
                                         MyMeetingReviewResponse myReview) {
        return ProjectHomeResponse.builder()
                .projectDetail(projectDetail)
                .meetingRecordList(meetingRecordList)
                .personalSpeakingList(personalSpeakingList)
                .myReview(myReview)
                .build();
    }

    public static ProjectHomeResponse notExistRecentReview(ProjectDetailResponse projectDetail) {
        return ProjectHomeResponse.builder()
                .projectDetail(projectDetail)
                .meetingRecordList(List.of())
                .personalSpeakingList(List.of())
                .myReview(null)
                .build();
    }
}
