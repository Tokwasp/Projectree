package ssafy.personal_audio_backend.domain.review.speech;

import java.util.Objects;
import ssafy.personal_audio_backend.domain.review.speech.exception.SpeechErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

public class SpeechSegment {

    private final double startSeconds;
    private final double endSeconds;

    private SpeechSegment(double startSeconds, double endSeconds) {
        this.startSeconds = startSeconds;
        this.endSeconds = endSeconds;
    }

    public static SpeechSegment of(double startSeconds, double endSeconds) {
        if (startSeconds < 0) {
            throw new CustomException(SpeechErrorCode.SPEECH_SEGMENT_NEGATIVE_START);
        }
        if (endSeconds <= startSeconds) {
            throw new CustomException(SpeechErrorCode.SPEECH_SEGMENT_INVALID_RANGE);
        }
        return new SpeechSegment(startSeconds, endSeconds);
    }

    public double durationSeconds() {
        return endSeconds - startSeconds;
    }

    public double silenceSecondsUntil(SpeechSegment next) {
        return Math.max(0.0, next.startSeconds - this.endSeconds);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SpeechSegment segment)) {
            return false;
        }
        return Double.compare(startSeconds, segment.startSeconds) == 0
                && Double.compare(endSeconds, segment.endSeconds) == 0;
    }

    @Override
    public int hashCode() {
        return Objects.hash(startSeconds, endSeconds);
    }

    @Override
    public String toString() {
        return "SpeechSegment(%.3f~%.3f)".formatted(startSeconds, endSeconds);
    }
}
