package com.ssafy.projectree.global.s3.dto.response;

import lombok.Getter;

@Getter
public class PresignedUrlResponse {

    private final String presignedUrl;
    private final String imageUrl;

    private PresignedUrlResponse(String presignedUrl, String imageUrl) {
        this.presignedUrl = presignedUrl;
        this.imageUrl = imageUrl;
    }

    public static PresignedUrlResponse of(String presignedUrl, String imageUrl) {
        return new PresignedUrlResponse(presignedUrl, imageUrl);
    }
}
