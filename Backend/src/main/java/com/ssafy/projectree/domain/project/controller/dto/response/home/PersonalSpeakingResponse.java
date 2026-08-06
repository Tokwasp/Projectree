package com.ssafy.projectree.domain.project.controller.dto.response.home;

import lombok.Builder;
import lombok.Getter;

@Getter
public class PersonalSpeakingResponse {
    private String name;
    private double speakPercent;

    @Builder
    private PersonalSpeakingResponse(String name, double speakPercent) {
        this.name = name;
        this.speakPercent = speakPercent;
    }

    public static PersonalSpeakingResponse of(String name, double speakPercent) {
        return PersonalSpeakingResponse.builder()
                .name(name)
                .speakPercent(speakPercent)
                .build();
    }
}
