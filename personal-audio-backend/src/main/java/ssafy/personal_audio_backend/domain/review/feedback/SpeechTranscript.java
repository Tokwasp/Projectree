package ssafy.personal_audio_backend.domain.review.feedback;

import ssafy.personal_audio_backend.domain.review.feedback.exception.FeedbackErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

/**
 * STT 로 받은 대본. 말하기 속도를 재는 근거가 된다.
 * <p>
 * 속도는 한글 음절 수를 무음 제외 발화 시간으로 나눠 구한다.
 * 영문과 숫자는 한 음절로 환산하기 어려워 세지 않는다.
 */
public class SpeechTranscript {

    private static final char HANGUL_SYLLABLE_FIRST = '가';
    private static final char HANGUL_SYLLABLE_LAST = '힣';
    private static final int SECONDS_PER_MINUTE = 60;
    private static final int UNKNOWN_SPEED = 0;

    private final String text;

    private SpeechTranscript(String text) {
        this.text = text;
    }

    public static SpeechTranscript of(String text) {
        if (text == null || text.isBlank()) {
            throw new CustomException(FeedbackErrorCode.TRANSCRIPT_EMPTY);
        }

        return new SpeechTranscript(text.trim());
    }

    public String text() {
        return text;
    }

    public int syllableCount() {
        return (int) text.chars()
                .filter(SpeechTranscript::isHangulSyllable)
                .count();
    }

    /**
     * 분당 음절수. 발화 시간을 모르면 0 을 돌려주고, 판단은 호출측이 건너뛴다.
     */
    public int syllablesPerMinute(int speakingSeconds) {
        if (speakingSeconds <= 0) {
            return UNKNOWN_SPEED;
        }

        return Math.toIntExact(Math.round(
                (double) syllableCount() * SECONDS_PER_MINUTE / speakingSeconds));
    }

    private static boolean isHangulSyllable(int codePoint) {
        return codePoint >= HANGUL_SYLLABLE_FIRST && codePoint <= HANGUL_SYLLABLE_LAST;
    }

    @Override
    public String toString() {
        return "SpeechTranscript(syllables=%d)".formatted(syllableCount());
    }
}
