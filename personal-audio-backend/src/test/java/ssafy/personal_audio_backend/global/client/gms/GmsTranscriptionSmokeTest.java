package ssafy.personal_audio_backend.global.client.gms;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
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
import ssafy.personal_audio_backend.domain.review.feedback.FillerWords;
import ssafy.personal_audio_backend.global.config.RestClientConfig;

@Slf4j
@SpringBootTest(classes = {GmsTranscriptionSmokeTest.SmokeConfig.class, RestClientConfig.class})
class GmsTranscriptionSmokeTest {

    private static final String EMPTY = "";

    @Autowired
    private RestClient gmsRestClient;

    @Value("${GMS_SMOKE_AUDIO:}")
    private String audioPath;

    @Value("${app.ai.gms.base-url}")
    private String baseUrl;

    @Value("${app.ai.gms.transcribe-model}")
    private String transcribeModel;

    @Value("${app.ai.gms.max-upload-bytes}")
    private long maxUploadBytes;

    @DisplayName("Whisper 로 대본을 만들고 간투사와 인식 확신도를 확인한다")
    @Test
    void transcribe() {
        assumeTrue(StringUtils.hasText(baseUrl), "GMS_BASE_URL 을 .env 에 채우면 실행된다");
        assumeTrue(StringUtils.hasText(audioPath), "GMS_SMOKE_AUDIO 를 .env 에 채우면 실행된다");

        Path audioFile = Path.of(audioPath);
        assertThat(Files.exists(audioFile))
                .as("GMS_SMOKE_AUDIO 경로에 파일이 있어야 한다: %s", audioPath)
                .isTrue();

        GmsTranscription transcription =
                new GmsTranscriptionClient(gmsRestClient, transcribeModel, maxUploadBytes)
                        .transcribe(audioFile, FillerWords.transcriptionHint());

        log.info("whisper smoke result.\n{}", report(transcription));
        assertThat(transcription.hasText()).isTrue();
    }

    private String report(GmsTranscription transcription) {
        return """

                ─────────── 요약 ───────────
                language        : %s
                duration        : %.2f초
                segmentCount    : %d
                averageLogprob  : %.3f   (0 에 가까울수록 또렷하게 인식)
                간투사(명확)    : %s
                간투사(문맥의존): %s
                (사전 %d개 = 명확 %d + 문맥의존 %d)

                ─────────── 대본 전문 ───────────
                %s

                ─────────── 세그먼트별 ───────────
                %s
                """.formatted(
                transcription.getLanguage(),
                transcription.getDuration(),
                transcription.segmentCount(),
                transcription.averageLogprob(),
                fillerReport(FillerWords.tallyClear(transcription.getText())),
                fillerReport(FillerWords.tallyAmbiguous(transcription.getText())),
                FillerWords.size(),
                FillerWords.clearSize(),
                FillerWords.size() - FillerWords.clearSize(),
                transcription.getText(),
                segmentReport(transcription.getSegments()));
    }

    private String fillerReport(Map<String, Long> tally) {
        if (tally.isEmpty()) {
            return "0개";
        }

        long total = tally.values().stream().mapToLong(Long::longValue).sum();

        return tally.entrySet().stream()
                .map(entry -> "%s×%d".formatted(entry.getKey(), entry.getValue()))
                .collect(Collectors.joining(", ", "%d개 — ".formatted(total), EMPTY));
    }

    private String segmentReport(List<GmsTranscription.Segment> segments) {
        if (segments == null || segments.isEmpty()) {
            return "(없음 — response_format 이 verbose_json 으로 처리되지 않았을 수 있다)";
        }

        return segments.stream()
                .map(segment -> "[%6.2f~%6.2f] logprob=%6.3f noSpeech=%.3f  %s".formatted(
                        segment.getStart(), segment.getEnd(),
                        segment.getAvgLogprob(), segment.getNoSpeechProb(), segment.getText()))
                .collect(Collectors.joining("\n"));
    }

    @Configuration
    static class SmokeConfig {

        @Bean
        static PropertySourcesPlaceholderConfigurer propertySourcesPlaceholderConfigurer() {
            return new PropertySourcesPlaceholderConfigurer();
        }
    }
}
