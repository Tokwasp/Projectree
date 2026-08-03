package com.ssafy.projectree.global.config.session;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Getter
@ConfigurationProperties(prefix = "naver")
@RequiredArgsConstructor
public class NaverOAuthProperties {

    private final String clientId;
    private final String clientSecret;
    private final String tokenUri;
    private final String userinfoUri;
}
