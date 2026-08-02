package ssafy.personal_audio_backend.domain.review.feedback;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import ssafy.personal_audio_backend.global.exception.CustomException;

class SpeechFeedbackTest {

    @DisplayName("피드백 세 줄을 그대로 담는다")
    @Test
    void of() {
        SpeechFeedback feedback = SpeechFeedback.of("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요");

        assertThat(feedback.speed()).isEqualTo("조금 빠릅니다");
        assertThat(feedback.personal()).isEqualTo("간투사가 잦아요");
        assertThat(feedback.overall()).isEqualTo("속도만 줄이면 좋겠어요");
        assertThat(feedback.isEmpty()).isFalse();
    }

    @DisplayName("앞뒤 공백과 줄바꿈을 정리한다")
    @Test
    void ofNormalizesWhitespace() {
        SpeechFeedback feedback = SpeechFeedback.of("  조금\n빠릅니다  ", "간투사가   잦아요", "좋아요");

        assertThat(feedback.speed()).isEqualTo("조금 빠릅니다");
        assertThat(feedback.personal()).isEqualTo("간투사가 잦아요");
    }

    @DisplayName("속도는 40자, 말버릇은 65자로 자른다")
    @Test
    void ofTruncatesShortFeedback() {
        String tooLong = "가".repeat(80);

        SpeechFeedback feedback = SpeechFeedback.of(tooLong, tooLong, "좋아요");

        assertThat(feedback.speed()).hasSize(40);
        assertThat(feedback.personal()).hasSize(65);
    }

    @DisplayName("종합 피드백은 60자로 자른다")
    @Test
    void ofTruncatesOverallFeedback() {
        SpeechFeedback feedback = SpeechFeedback.of("빠릅니다", "잦아요", "가".repeat(80));

        assertThat(feedback.overall()).hasSize(60);
    }

    @DisplayName("목표 길이 안의 따뜻한 문구는 그대로 둔다")
    @Test
    void ofKeepsWarmFeedbackAsIs() {
        SpeechFeedback feedback = SpeechFeedback.of(
                "조금 느리지만 편안하게 들려요",
                "말하기 전에 아.. 하시는 습관이 있는 것 같아요. 조금 줄이면 더 좋을 것 같아요",
                "차분하고 듣는 사람을 배려하는 말투예요. 좋습니다!");

        assertThat(feedback.speed()).isEqualTo("조금 느리지만 편안하게 들려요");
        assertThat(feedback.personal())
                .isEqualTo("말하기 전에 아.. 하시는 습관이 있는 것 같아요. 조금 줄이면 더 좋을 것 같아요");
        assertThat(feedback.overall()).isEqualTo("차분하고 듣는 사람을 배려하는 말투예요. 좋습니다!");
    }

    @DisplayName("일부 항목이 비어도 나머지가 있으면 만들어진다")
    @Test
    void ofWithPartiallyEmptyFeedback() {
        SpeechFeedback feedback = SpeechFeedback.of(null, "", "간투사가 잦아요");

        assertThat(feedback.speed()).isEmpty();
        assertThat(feedback.personal()).isEmpty();
        assertThat(feedback.overall()).isEqualTo("간투사가 잦아요");
        assertThat(feedback.isEmpty()).isFalse();
    }

    @DisplayName("세 항목이 모두 비면 예외를 던진다")
    @Test
    void ofWithAllEmptyFeedback() {
        assertThatThrownBy(() -> SpeechFeedback.of(null, "   ", ""))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 내용이 비어 있습니다.");
    }

    @DisplayName("빈 피드백은 비어 있음으로 표시된다")
    @Test
    void none() {
        SpeechFeedback feedback = SpeechFeedback.none();

        assertThat(feedback.isEmpty()).isTrue();
        assertThat(feedback.overall()).isEmpty();
    }
}
