package ssafy.personal_audio_backend.domain.review.feedback;

import java.util.Objects;
import ssafy.personal_audio_backend.domain.review.feedback.exception.FeedbackErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

public class SpeechFeedback {

    private static final int SHORT_MAX_LENGTH = 40;
    private static final int OVERALL_MAX_LENGTH = 60;
    private static final String WHITESPACE = "\\s+";
    private static final String SINGLE_SPACE = " ";
    private static final String EMPTY = "";

    private final String speed;
    private final String personal;
    private final String overall;

    private SpeechFeedback(String speed, String personal, String overall) {
        this.speed = speed;
        this.personal = personal;
        this.overall = overall;
    }

    public static SpeechFeedback of(String speed, String personal, String overall) {
        SpeechFeedback feedback = new SpeechFeedback(
                normalize(speed, SHORT_MAX_LENGTH),
                normalize(personal, SHORT_MAX_LENGTH),
                normalize(overall, OVERALL_MAX_LENGTH)
        );
        if (feedback.isEmpty()) {
            throw new CustomException(FeedbackErrorCode.FEEDBACK_EMPTY);
        }

        return feedback;
    }

    public static SpeechFeedback none() {
        return new SpeechFeedback(EMPTY, EMPTY, EMPTY);
    }

    public boolean isEmpty() {
        return speed.isEmpty() && personal.isEmpty() && overall.isEmpty();
    }

    public String speed() {
        return speed;
    }

    public String personal() {
        return personal;
    }

    public String overall() {
        return overall;
    }

    private static String normalize(String raw, int maxLength) {
        if (raw == null) {
            return EMPTY;
        }

        String collapsed = raw.replaceAll(WHITESPACE, SINGLE_SPACE).trim();
        if (collapsed.length() <= maxLength) {
            return collapsed;
        }

        return collapsed.substring(0, maxLength);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SpeechFeedback feedback)) {
            return false;
        }
        return Objects.equals(speed, feedback.speed)
                && Objects.equals(personal, feedback.personal)
                && Objects.equals(overall, feedback.overall);
    }

    @Override
    public int hashCode() {
        return Objects.hash(speed, personal, overall);
    }

    @Override
    public String toString() {
        return "SpeechFeedback(speed=%s, personal=%s, overall=%s)"
                .formatted(speed, personal, overall);
    }
}
