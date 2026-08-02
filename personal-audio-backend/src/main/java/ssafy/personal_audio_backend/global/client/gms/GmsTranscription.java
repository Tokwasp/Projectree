package ssafy.personal_audio_backend.global.client.gms;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Whisper 의 verbose_json 응답. 대본과 세그먼트별 인식 확신도를 함께 담는다.
 */
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@JsonIgnoreProperties(ignoreUnknown = true)
public class GmsTranscription {

    private String text;
    private String language;
    private double duration;
    private List<Segment> segments;

    public boolean hasText() {
        return text != null && !text.isBlank();
    }

    public int segmentCount() {
        return segments == null ? 0 : segments.size();
    }

    /**
     * 세그먼트별 avg_logprob 의 평균. 0 에 가까울수록 또렷하게 인식한 것이다.
     * 마이크 품질과 소음에도 함께 반응하므로 발음 판단의 간접 신호로만 쓴다.
     */
    public double averageLogprob() {
        if (segmentCount() == 0) {
            return 0.0;
        }

        return segments.stream()
                .mapToDouble(Segment::getAvgLogprob)
                .average()
                .orElse(0.0);
    }

    @Getter
    @NoArgsConstructor(access = AccessLevel.PROTECTED)
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Segment {

        private double start;
        private double end;
        private String text;

        @JsonProperty("avg_logprob")
        private double avgLogprob;

        @JsonProperty("no_speech_prob")
        private double noSpeechProb;
    }
}
