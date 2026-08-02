package ssafy.personal_audio_backend.domain.review.feedback;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class FillerWordsTest {

    @DisplayName("사전은 명확한 간투사와 문맥의존 간투사로 나뉜다")
    @Test
    void size() {
        assertThat(FillerWords.size()).isEqualTo(56);
        assertThat(FillerWords.clearSize()).isEqualTo(24);
    }

    @DisplayName("명확한 간투사만 많은 순으로 센다")
    @Test
    void tallyClear() {
        String text = "어 어 음 안녕하세요 그냥 어";

        assertThat(FillerWords.tallyClear(text))
                .containsExactly(entry("어", 3L), entry("음", 1L));
    }

    @DisplayName("문맥의존 간투사는 따로 센다")
    @Test
    void tallyAmbiguous() {
        String text = "어 그냥 그냥 약간 안녕하세요";

        assertThat(FillerWords.tallyAmbiguous(text))
                .containsExactly(entry("그냥", 2L), entry("약간", 1L));
    }

    @DisplayName("구두점이 붙어도 간투사로 센다")
    @Test
    void tallyIgnoresPunctuation() {
        String text = "어… 음, 그.";

        assertThat(total(FillerWords.tallyClear(text))).isEqualTo(3);
    }

    @DisplayName("조사가 붙은 형태는 세지 않는다")
    @Test
    void tallyDoesNotMatchInflectedForm() {
        String text = "약간은 그냥요";

        assertThat(FillerWords.tallyClear(text)).isEmpty();
        assertThat(FillerWords.tallyAmbiguous(text)).isEmpty();
    }

    @DisplayName("대본이 비어 있으면 0개로 센다")
    @Test
    void tallyWithBlankText() {
        assertThat(FillerWords.tallyClear(null)).isEmpty();
        assertThat(FillerWords.tallyClear("   ")).isEmpty();
    }

    private long total(java.util.Map<String, Long> tally) {
        return tally.values().stream().mapToLong(Long::longValue).sum();
    }

    @DisplayName("축자 전사 힌트에 간투사 예시가 들어 있다")
    @Test
    void transcriptionHint() {
        assertThat(FillerWords.transcriptionHint()).contains("어", "음", "그러니까");
    }

    private static java.util.Map.Entry<String, Long> entry(String key, Long value) {
        return java.util.Map.entry(key, value);
    }
}
