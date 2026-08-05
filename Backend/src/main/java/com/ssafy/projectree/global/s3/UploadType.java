package com.ssafy.projectree.global.s3;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

@Getter
@RequiredArgsConstructor
public enum UploadType {
    PROFILE("프로필", "profile"),
    PROJECT("프로젝트", "project");

    private final String description;

    private final String directory;
}
