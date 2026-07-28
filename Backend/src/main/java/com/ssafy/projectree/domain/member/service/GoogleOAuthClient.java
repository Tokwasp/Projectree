package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import com.ssafy.projectree.global.config.session.GoogleOAuthProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
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

    public GoogleTokenResponse exchangeCode(String code, String redirectUri) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("code", code);
        form.add("client_id", properties.getClientId());
        form.add("client_secret", properties.getClientSecret());
        form.add("redirect_uri", redirectUri);
        form.add("grant_type", GRANT_TYPE_AUTHORIZATION_CODE);

        return restClient.post()
                .uri(properties.getTokenUri())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .body(GoogleTokenResponse.class);
    }

    public GoogleUserInfoResponse getUserInfo(String accessToken) {
        return restClient.get()
                .uri(properties.getUserinfoUri())
                .header(HttpHeaders.AUTHORIZATION, BEARER_PREFIX + accessToken)
                .retrieve()
                .body(GoogleUserInfoResponse.class);
    }
}
