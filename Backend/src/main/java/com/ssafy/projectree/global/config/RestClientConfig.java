package com.ssafy.projectree.global.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(GoogleOAuthProperties.class)
public class RestClientConfig {

    @Bean
    public RestClient restClient() {
        return RestClient.create();
    }
}
