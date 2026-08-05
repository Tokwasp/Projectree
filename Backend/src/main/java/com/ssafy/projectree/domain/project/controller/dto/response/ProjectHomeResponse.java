package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.meetingreview.dto.response.MeetingRecordResponse;
import com.ssafy.projectree.domain.meetingreview.dto.response.MyMeetingReviewResponse;
import com.ssafy.projectree.domain.meetingreview.dto.response.PersonalSpeakingResponse;
import lombok.Builder;
import lombok.Getter;

import java.util.List;

@Getter
public class ProjectHomeResponse {

    private List<MeetingRecordResponse> meetingRecordList;
    private List<PersonalSpeakingResponse> personalSpeakingList;
    private MyMeetingReviewResponse myReview;

    @Builder
    private ProjectHomeResponse(List<MeetingRecordResponse> meetingRecordList,
                               List<PersonalSpeakingResponse> personalSpeakingList,
                               MyMeetingReviewResponse myReview) {
        this.meetingRecordList = meetingRecordList;
        this.personalSpeakingList = personalSpeakingList;
        this.myReview = myReview;
    }

    public static ProjectHomeResponse of(List<MeetingRecordResponse> meetingRecordList,
                                         List<PersonalSpeakingResponse> personalSpeakingList,
                                         MyMeetingReviewResponse myReview) {
        return ProjectHomeResponse.builder()
                .meetingRecordList(meetingRecordList)
                .personalSpeakingList(personalSpeakingList)
                .myReview(myReview)
                .build();
    }

    public static ProjectHomeResponse empty() {
        return ProjectHomeResponse.builder()
                .meetingRecordList(List.of())
                .personalSpeakingList(List.of())
                .myReview(null)
                .build();
    }
}
