package com.ssafy.projectree.domain.meetingreview.dto.response;

import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import lombok.Builder;
import lombok.Getter;

@Getter
public class MyMeetingReviewResponse {
    private String speedFeedback;
    private String personalFeedback;
    private String overallFeedback;

    @Builder
    private MyMeetingReviewResponse(String speedFeedback, String personalFeedback, String overallFeedback){
        this.speedFeedback = speedFeedback;
        this.personalFeedback = personalFeedback;
        this.overallFeedback = overallFeedback;
    }

    public static MyMeetingReviewResponse of(MeetingReview review){
        return MyMeetingReviewResponse.builder()
                .speedFeedback(review.getSpeedFeedback())
                .personalFeedback(review.getPersonalFeedback())
                .overallFeedback(review.getOverallFeedback())
                .build();
    }
}
