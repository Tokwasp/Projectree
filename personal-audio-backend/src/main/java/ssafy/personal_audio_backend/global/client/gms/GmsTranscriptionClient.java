package ssafy.personal_audio_backend.global.client.gms;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import ssafy.personal_audio_backend.global.client.gms.exception.GmsErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

/**
 * GMS 의 audio/transcriptions 로 녹음 파일을 대본으로 바꾼다.
 * <p>
 * Whisper 는 ogg 를 그대로 받으므로 mp3 변환 없이 원본을 보낸다.
 * 다만 파일 크기 상한(25MB)이 있어 긴 녹음은 잘라 보내야 한다.
 */
@Slf4j
@Component
public class GmsTranscriptionClient {

    private static final String TRANSCRIPTIONS_PATH = "/v1/audio/transcriptions";
    private static final String VERBOSE_JSON = "verbose_json";
    private static final String KOREAN = "ko";
    private static final String NO_SAMPLING = "0";
    private static final int ERROR_BODY_LOG_LIMIT = 200;

    private final RestClient gmsRestClient;
    private final String model;
    private final long maxUploadBytes;

    public GmsTranscriptionClient(
            RestClient gmsRestClient,
            @Value("${app.ai.gms.transcribe-model}") String model,
            @Value("${app.ai.gms.max-upload-bytes}") long maxUploadBytes) {
        this.gmsRestClient = gmsRestClient;
        this.model = model;
        this.maxUploadBytes = maxUploadBytes;
    }

    /**
     * @param stylePrompt 어떤 말투로 받아적을지 알려주는 힌트. 지시문이 아니라 표기 예시다.
     */
    public GmsTranscription transcribe(Path audioFile, String stylePrompt) {
        verifyUploadable(audioFile);

        GmsTranscription transcription = send(audioFile, stylePrompt);
        if (transcription == null || !transcription.hasText()) {
            log.warn("gms transcription is empty. model={}, file={}", model, audioFile);
            throw new CustomException(GmsErrorCode.GMS_RESPONSE_INVALID);
        }

        return transcription;
    }

    /**
     * 상한을 넘으면 호출 전에 막는다. 넘긴 채로 보내면 업스트림이 본문 없는 400 을 돌려줘 원인을 알기 어렵다.
     */
    private void verifyUploadable(Path audioFile) {
        long size;
        try {
            size = Files.size(audioFile);
        } catch (IOException e) {
            log.warn("failed to read audio size. file={}, cause={}", audioFile, e.toString());
            throw new CustomException(GmsErrorCode.GMS_REQUEST_FAILED);
        }

        if (size > maxUploadBytes) {
            log.warn("audio too large for transcription. file={}, size={}, limit={}",
                    audioFile, size, maxUploadBytes);
            throw new CustomException(GmsErrorCode.GMS_AUDIO_TOO_LARGE);
        }
    }

    private GmsTranscription send(Path audioFile, String stylePrompt) {
        try {
            return gmsRestClient.post()
                    .uri(TRANSCRIPTIONS_PATH)
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(multipartBody(audioFile, stylePrompt))
                    .retrieve()
                    .body(GmsTranscription.class);
        } catch (RestClientResponseException e) {
            log.warn("gms transcription failed. model={}, status={}, body={}",
                    model, e.getStatusCode(), abbreviate(e.getResponseBodyAsString()));
            throw new CustomException(GmsErrorCode.GMS_REQUEST_FAILED);
        } catch (ResourceAccessException e) {
            log.warn("gms transcription timed out. model={}, cause={}", model, e.getMessage());
            throw new CustomException(GmsErrorCode.GMS_TIMEOUT);
        } catch (RestClientException e) {
            log.warn("gms transcription call failed. model={}, cause={}", model, e.toString());
            throw new CustomException(GmsErrorCode.GMS_REQUEST_FAILED);
        }
    }

    private Object multipartBody(Path audioFile, String stylePrompt) {
        MultipartBodyBuilder bodyBuilder = new MultipartBodyBuilder();
        bodyBuilder.part("file", new FileSystemResource(audioFile));
        bodyBuilder.part("model", model);
        bodyBuilder.part("response_format", VERBOSE_JSON);
        bodyBuilder.part("language", KOREAN);
        bodyBuilder.part("temperature", NO_SAMPLING);
        bodyBuilder.part("prompt", stylePrompt);

        return bodyBuilder.build();
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
