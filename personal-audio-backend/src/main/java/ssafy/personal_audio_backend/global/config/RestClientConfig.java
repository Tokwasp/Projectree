package ssafy.personal_audio_backend.global.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.BufferingClientHttpRequestFactory;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(10);
    private static final String BEARER_PREFIX = "Bearer ";

    @Bean
    public RestClient gmsRestClient(
            @Value("${app.ai.gms.base-url}") String baseUrl,
            @Value("${app.ai.gms.api-key}") String apiKey,
            @Value("${app.ai.gms.timeout}") Duration timeout) {
        return RestClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.AUTHORIZATION, BEARER_PREFIX + apiKey)
                .requestFactory(requestFactory(timeout))
                .build();
    }

    private ClientHttpRequestFactory requestFactory(Duration readTimeout) {
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(
                HttpClient.newBuilder()
                        .connectTimeout(CONNECT_TIMEOUT)
                        .build());
        requestFactory.setReadTimeout(readTimeout);

        return new BufferingClientHttpRequestFactory(requestFactory);
    }
}
