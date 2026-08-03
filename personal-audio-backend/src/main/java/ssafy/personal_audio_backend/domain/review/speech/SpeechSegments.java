package ssafy.personal_audio_backend.domain.review.speech;

import static java.util.function.Predicate.not;

import java.util.List;

public class SpeechSegments {

    private final List<SpeechSegment> segments;

    private SpeechSegments(List<SpeechSegment> segments) {
        this.segments = segments;
    }

    /**
     * 0.5초 미만의 짧은 구간은 주변 소음으로 보고 제외한다.
     */
    public static SpeechSegments of(List<SpeechSegment> segments) {
        return new SpeechSegments(segments.stream()
                .filter(not(SpeechSegment::isNoise))
                .toList());
    }

    public int speakingSeconds() {
        double total = segments.stream()
                .mapToDouble(SpeechSegment::durationSeconds)
                .sum();
        return toSeconds(total);
    }

    public int segmentCount() {
        return segments.size();
    }

    private int toSeconds(double seconds) {
        return Math.toIntExact(Math.round(seconds));
    }

    @Override
    public String toString() {
        return "SpeechSegments(count=%d, speakingSeconds=%d)".formatted(segmentCount(), speakingSeconds());
    }
}
