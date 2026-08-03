package com.ssafy.projectree.global.config.s3;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@ConfigurationProperties(prefix = "app.s3")
@RequiredArgsConstructor
public class S3Properties {

    private final String bucket;

    private final long presignedUrlExpireSeconds;
}
