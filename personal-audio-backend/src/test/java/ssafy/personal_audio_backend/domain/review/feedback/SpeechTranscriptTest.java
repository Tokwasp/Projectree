package ssafy.personal_audio_backend.domain.review.feedback;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import ssafy.personal_audio_backend.global.exception.CustomException;

class SpeechTranscriptTest {

    @DisplayName("한글 음절만 센다")
    @Test
    void syllableCount() {
        SpeechTranscript transcript = SpeechTranscript.of("안녕하세요 반갑습니다");

        assertThat(transcript.syllableCount()).isEqualTo(10);
    }

    @DisplayName("공백과 구두점, 영문과 숫자는 음절로 세지 않는다")
    @Test
    void syllableCountIgnoresNonHangul() {
        SpeechTranscript transcript = SpeechTranscript.of("안녕하세요! API 3개를 봅니다.");

        assertThat(transcript.syllableCount()).isEqualTo(10);
    }

    @DisplayName("분당 음절수를 발화 시간으로 나눠 구한다")
    @Test
    void syllablesPerMinute() {
        SpeechTranscript transcript = SpeechTranscript.of("안녕하세요 반갑습니다");

        assertThat(transcript.syllablesPerMinute(10)).isEqualTo(60);
        assertThat(transcript.syllablesPerMinute(2)).isEqualTo(300);
    }

    @DisplayName("발화 시간이 0이면 속도를 알 수 없으므로 0을 돌려준다")
    @Test
    void syllablesPerMinuteWithoutSpeakingTime() {
        SpeechTranscript transcript = SpeechTranscript.of("안녕하세요");

        assertThat(transcript.syllablesPerMinute(0)).isZero();
        assertThat(transcript.syllablesPerMinute(-1)).isZero();
    }

    @DisplayName("앞뒤 공백을 정리한다")
    @Test
    void ofTrimsText() {
        SpeechTranscript transcript = SpeechTranscript.of("  안녕하세요  ");

        assertThat(transcript.text()).isEqualTo("안녕하세요");
    }

    @DisplayName("대본이 비어 있으면 예외를 던진다")
    @Test
    void ofWithBlankText() {
        assertThatThrownBy(() -> SpeechTranscript.of("   "))
                .isInstanceOf(CustomException.class)
                .hasMessage("음성에서 대본을 얻지 못했습니다.");
    }
}
