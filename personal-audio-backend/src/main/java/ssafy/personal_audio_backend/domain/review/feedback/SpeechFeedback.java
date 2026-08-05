package ssafy.personal_audio_backend.domain.review.feedback;

import java.util.Objects;
import ssafy.personal_audio_backend.domain.review.feedback.exception.FeedbackErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

public class SpeechFeedback {

    private static final int SPEED_MAX_LENGTH = 25;
    private static final int PERSONAL_MAX_LENGTH = 35;
    private static final int OVERALL_MAX_LENGTH = 40;
    private static final String WHITESPACE = "\\s+";
    /** 프롬프트로 금지해도 모델이 굽은 따옴표로 우회하므로 여기서 지운다. */
    private static final String QUOTES = "[\"'“”‘’«»「」`]";
    private static final String SENTENCE_ENDS = ".!?";
    /** 문장만 남겼을 때 이보다 짧아지면 말이 너무 없어져 문장 경계를 포기한다. */
    private static final int MIN_KEPT_LENGTH = 12;
    private static final int NOT_FOUND = -1;
    private static final char SPACE = ' ';
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
                normalize(speed, SPEED_MAX_LENGTH),
                normalize(personal, PERSONAL_MAX_LENGTH),
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

        String collapsed = raw.replaceAll(QUOTES, EMPTY)
                .replaceAll(WHITESPACE, SINGLE_SPACE)
                .trim();
        if (collapsed.length() <= maxLength) {
            return collapsed;
        }

        return truncate(collapsed, maxLength);
    }

    /**
     * 한도를 넘기면 완성된 문장까지만 남기고 뒤에 걸친 문장은 버린다.
     * <p>
     * 문장 경계가 없거나 너무 앞이면 적어도 어절 경계에서 끊는다. 말이 단어 중간에서 잘리면 읽는 사람이 불안하다.
     */
    private static String truncate(String text, int maxLength) {
        String cut = text.substring(0, maxLength);

        int sentenceEnd = lastSentenceEndIn(cut);
        if (sentenceEnd != NOT_FOUND && sentenceEnd + 1 >= MIN_KEPT_LENGTH) {
            return cut.substring(0, sentenceEnd + 1);
        }

        int wordEnd = cut.lastIndexOf(SPACE);
        if (wordEnd > 0) {
            return cut.substring(0, wordEnd);
        }

        return cut;
    }

    private static int lastSentenceEndIn(String text) {
        for (int i = text.length() - 1; i >= 0; i--) {
            if (SENTENCE_ENDS.indexOf(text.charAt(i)) >= 0) {
                return i;
            }
        }

        return NOT_FOUND;
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
