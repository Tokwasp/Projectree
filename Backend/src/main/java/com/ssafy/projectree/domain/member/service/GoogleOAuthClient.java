package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import com.ssafy.projectree.domain.member.exception.AuthErrorCode;
import com.ssafy.projectree.global.config.session.GoogleOAuthProperties;
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
public class GoogleOAuthClient {

    private static final String GRANT_TYPE_AUTHORIZATION_CODE = "authorization_code";
    private static final String BEARER_PREFIX = "Bearer ";

    private final RestClient restClient;
    private final GoogleOAuthProperties properties;

    public GoogleTokenResponse getUserAccessToken(String code, String redirectUri) {
        MultiValueMap<String, String> requestMap = new LinkedMultiValueMap<>();
        requestMap.add("code", code);
        requestMap.add("client_id", properties.getClientId());
        requestMap.add("client_secret", properties.getClientSecret());
        requestMap.add("redirect_uri", redirectUri);
        requestMap.add("grant_type", GRANT_TYPE_AUTHORIZATION_CODE);

        GoogleTokenResponse response = restClient.post()
                .uri(properties.getTokenUri())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(requestMap)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, errorResponse) -> {
                    throw new CustomException(AuthErrorCode.GOOGLE_TOKEN_FAILED);
                })
                .body(GoogleTokenResponse.class);

        if (response == null || response.getAccessToken() == null) {
            throw new CustomException(AuthErrorCode.GOOGLE_TOKEN_FAILED);
        }
        return response;
    }

    public GoogleUserInfoResponse getUserInfo(String accessToken) {
        GoogleUserInfoResponse response = restClient.get()
                .uri(properties.getUserinfoUri())
                .header(HttpHeaders.AUTHORIZATION, BEARER_PREFIX + accessToken)
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, errorResponse) -> {
                    throw new CustomException(AuthErrorCode.GOOGLE_PROFILE_FAILED);
                })
                .body(GoogleUserInfoResponse.class);

        if (response == null || response.getEmail() == null) {
            throw new CustomException(AuthErrorCode.GOOGLE_PROFILE_FAILED);
        }
        return response;
    }
}
