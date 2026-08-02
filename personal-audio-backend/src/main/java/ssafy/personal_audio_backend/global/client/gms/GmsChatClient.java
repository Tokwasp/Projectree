package ssafy.personal_audio_backend.global.client.gms;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import ssafy.personal_audio_backend.global.client.gms.exception.GmsErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

@Slf4j
@Component
public class GmsChatClient {

    private static final String CHAT_COMPLETIONS_PATH = "/v1/chat/completions";
    private static final int ERROR_BODY_LOG_LIMIT = 200;

    private final RestClient gmsRestClient;
    private final String model;

    public GmsChatClient(RestClient gmsRestClient, @Value("${app.ai.gms.model}") String model) {
        this.gmsRestClient = gmsRestClient;
        this.model = model;
    }

    /**
     * JSON 한 덩어리만 돌려받는다. 응답 본문 문자열을 그대로 반환하므로 파싱은 호출측 몫이다.
     */
    public String completeJson(String systemPrompt, String userText) {
        return contentOf(send(GmsChatRequest.jsonAnswer(model, systemPrompt, userText)));
    }

    private GmsChatResponse send(GmsChatRequest request) {
        try {
            return gmsRestClient.post()
                    .uri(CHAT_COMPLETIONS_PATH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(GmsChatResponse.class);
        } catch (RestClientResponseException e) {
            log.warn("gms request failed. model={}, status={}, body={}", model, e.getStatusCode(), abbreviate(e.getResponseBodyAsString()));
            throw new CustomException(GmsErrorCode.GMS_REQUEST_FAILED);
        } catch (ResourceAccessException e) {
            log.warn("gms request timed out. model={}, cause={}", model, e.getMessage());
            throw new CustomException(GmsErrorCode.GMS_TIMEOUT);
        } catch (RestClientException e) {
            log.warn("gms call failed. model={}, cause={}", model, e.toString());
            throw new CustomException(GmsErrorCode.GMS_REQUEST_FAILED);
        }
    }

    private String contentOf(GmsChatResponse response) {
        String content = response == null ? null : response.firstContent();
        if (!StringUtils.hasText(content)) {
            log.warn("gms response has no content. model={}", model);
            throw new CustomException(GmsErrorCode.GMS_RESPONSE_INVALID);
        }

        return content;
    }

    private String abbreviate(String body) {
        if (body == null) {
            return "";
        }
        if (body.length() <= ERROR_BODY_LOG_LIMIT) {
            return body;
        }

        return body.substring(0, ERROR_BODY_LOG_LIMIT) + "...";
    }
}
