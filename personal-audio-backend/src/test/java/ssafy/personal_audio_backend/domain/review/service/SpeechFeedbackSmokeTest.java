package ssafy.personal_audio_backend.domain.review.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.mockito.Mockito.mock;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.PropertySourcesPlaceholderConfigurer;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import software.amazon.awssdk.services.s3.S3Client;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegment;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.client.gms.GmsChatClient;
import ssafy.personal_audio_backend.global.client.gms.GmsTranscriptionClient;
import ssafy.personal_audio_backend.global.config.RestClientConfig;
import tools.jackson.databind.json.JsonMapper;

@Slf4j
@SpringBootTest(classes = {SpeechFeedbackSmokeTest.SmokeConfig.class, RestClientConfig.class})
class SpeechFeedbackSmokeTest {

    private static final String UNUSED_BUCKET = "unused";

    @Autowired
    private RestClient gmsRestClient;

    @Value("${GMS_SMOKE_AUDIO:}")
    private String audioPath;

    /** 실제 파이프라인에서는 ffmpeg 가 계산한다. 녹음 길이에 맞춰 .env 에서 조정한다. */
    @Value("${GMS_SMOKE_SPEAKING_SECONDS:30}")
    private double assumedSpeakingSeconds;

    @Value("${app.ai.gms.base-url}")
    private String baseUrl;

    @Value("${app.ai.gms.model}")
    private String model;

    @Value("${app.ai.gms.transcribe-model}")
    private String transcribeModel;

    @Value("${app.ai.gms.max-upload-bytes}")
    private long maxUploadBytes;

    @Value("${app.ai.audio.max-seconds}")
    private long maxSeconds;

    @Value("${app.ai.audio.convert-timeout}")
    private Duration convertTimeout;

    @DisplayName("녹음 하나로 STT 부터 피드백 세 줄까지 실제로 만들어 본다")
    @Test
    void generate() {
        assumeTrue(StringUtils.hasText(baseUrl), "GMS_BASE_URL 을 .env 에 채우면 실행된다");
        assumeTrue(StringUtils.hasText(audioPath), "GMS_SMOKE_AUDIO 를 .env 에 채우면 실행된다");

        Path audioFile = Path.of(audioPath);
        assertThat(Files.exists(audioFile))
                .as("GMS_SMOKE_AUDIO 경로에 파일이 있어야 한다: %s", audioPath)
                .isTrue();

        log.info("feedback smoke start. transcribeModel={}, chatModel={}", transcribeModel, model);
        SpeechFeedback feedback = speechFeedbackService().generate(audioFile, assumedSegments());

        log.info("""
                feedback smoke result.
                  speed    : {}
                  personal : {}
                  overall  : {}""", feedback.speed(), feedback.personal(), feedback.overall());
        assertThat(feedback.isEmpty()).isFalse();
    }

    private SpeechFeedbackService speechFeedbackService() {
        return new SpeechFeedbackService(
                new GmsTranscriptionClient(gmsRestClient, transcribeModel, maxUploadBytes),
                new GmsChatClient(gmsRestClient, model),
                new FfmpegAudioConverter(maxSeconds, convertTimeout),
                new RecordingFileService(mock(S3Client.class), UNUSED_BUCKET),
                JsonMapper.builder().build());
    }

    private SpeechSegments assumedSegments() {
        return SpeechSegments.of(List.of(SpeechSegment.of(0.0, assumedSpeakingSeconds)));
    }

    @Configuration
    static class SmokeConfig {

        @Bean
        static PropertySourcesPlaceholderConfigurer propertySourcesPlaceholderConfigurer() {
            return new PropertySourcesPlaceholderConfigurer();
        }
    }
}
