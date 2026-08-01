package ssafy.personal_audio_backend.domain.speech;

import java.util.List;

public class SpeechSegments {

    private final List<SpeechSegment> segments;

    private SpeechSegments(List<SpeechSegment> segments) {
        this.segments = segments;
    }

    public static SpeechSegments of(List<SpeechSegment> segments) {
        return new SpeechSegments(List.copyOf(segments));
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

    public int longestSilenceSeconds() {
        double longest = 0.0;
        for (int i = 0; i < segments.size() - 1; i++) {
            longest = Math.max(longest, segments.get(i).silenceSecondsUntil(segments.get(i + 1)));
        }
        return toSeconds(longest);
    }

    private int toSeconds(double seconds) {
        return Math.toIntExact(Math.round(seconds));
    }

    @Override
    public String toString() {
        return "SpeechSegments(count=%d, speakingSeconds=%d)".formatted(segmentCount(), speakingSeconds());
    }
}
