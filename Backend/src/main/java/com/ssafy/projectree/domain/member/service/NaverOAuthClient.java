package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.controller.response.session.NaverTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.NaverUserInfoResponse;
import com.ssafy.projectree.domain.member.exception.AuthErrorCode;
import com.ssafy.projectree.global.config.session.NaverOAuthProperties;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

@Component
@RequiredArgsConstructor
public class NaverOAuthClient {

    private static final String GRANT_TYPE_AUTHORIZATION_CODE = "authorization_code";
    private static final String BEARER_PREFIX = "Bearer ";

    private final RestClient restClient;
    private final NaverOAuthProperties properties;

    public NaverTokenResponse getUserAccessToken(String code, String state) {
        MultiValueMap<String, String> requestMap = new LinkedMultiValueMap<>();
        requestMap.add("grant_type", GRANT_TYPE_AUTHORIZATION_CODE);
        requestMap.add("client_id", properties.getClientId());
        requestMap.add("client_secret", properties.getClientSecret());
        requestMap.add("code", code);
        requestMap.add("state", state);

        NaverTokenResponse response = restClient.post()
                .uri(properties.getTokenUri())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(requestMap)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, errorResponse) -> {
                    throw new CustomException(AuthErrorCode.NAVER_TOKEN_FAILED);
                })
                .body(NaverTokenResponse.class);

        if (response == null || response.isFailed()) {
            throw new CustomException(AuthErrorCode.NAVER_TOKEN_FAILED);
        }
        return response;
    }

    public NaverUserInfoResponse getUserInfo(String accessToken) {
        NaverUserInfoResponse response = restClient.get()
                .uri(properties.getUserinfoUri())
                .header(HttpHeaders.AUTHORIZATION, BEARER_PREFIX + accessToken)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, errorResponse) -> {
                    throw new CustomException(AuthErrorCode.NAVER_PROFILE_FAILED);
                })
                .body(NaverUserInfoResponse.class);

        if (response == null || response.isFailed()) {
            throw new CustomException(AuthErrorCode.NAVER_PROFILE_FAILED);
        }
        return response;
    }
}
