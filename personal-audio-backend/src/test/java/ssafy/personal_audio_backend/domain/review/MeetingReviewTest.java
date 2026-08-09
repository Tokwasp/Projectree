package ssafy.personal_audio_backend.domain.review;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegment;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;

class MeetingReviewTest {

    private static final String ROOM_NAME = "efb9541a-97fc-4647-9de2-80873b708c0c";
    private static final int PROJECT_ID = 5;
    private static final int MEMBER_ID = 7;
    private static final String EGRESS_ID = "EG_YEMSyA8vLjac";
    private static final String[] FEEDBACK_FIELDS = {"speedFeedback", "personalFeedback", "overallFeedback"};

    @DisplayName("같은 녹음이 다시 들어오면 이미 반영한 것으로 본다")
    @Test
    void isAlreadyApplied() {
        MeetingReview review = MeetingReview.of(ROOM_NAME, PROJECT_ID, MEMBER_ID);
        review.add(segments(), EGRESS_ID);

        assertThat(review.isAlreadyApplied(EGRESS_ID)).isTrue();
        assertThat(review.isAlreadyApplied("EG_other")).isFalse();
    }

    @DisplayName("녹음이 여러 번 들어오면 발화량을 누적한다")
    @Test
    void add() {
        MeetingReview review = MeetingReview.of(ROOM_NAME, PROJECT_ID, MEMBER_ID);

        review.add(segments(), EGRESS_ID);
        review.add(segments(), "EG_second");

        assertThat(review.getSpeakingSeconds()).isEqualTo(6);
    }

    @DisplayName("피드백 세 줄을 저장한다")
    @Test
    void applyFeedback() {
        MeetingReview review = MeetingReview.of(ROOM_NAME, PROJECT_ID, MEMBER_ID);

        review.applyFeedback(SpeechFeedback.of("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요"));

        assertThat(review).extracting(FEEDBACK_FIELDS)
                .containsExactly("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요");
    }

    @DisplayName("새 피드백이 들어오면 이전 피드백을 덮어쓴다")
    @Test
    void applyFeedbackOverwritesPreviousOne() {
        MeetingReview review = MeetingReview.of(ROOM_NAME, PROJECT_ID, MEMBER_ID);
        review.applyFeedback(SpeechFeedback.of("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요"));

        review.applyFeedback(SpeechFeedback.of("속도가 적절해요", "간투사가 줄었어요", "지난번보다 나아졌어요"));

        assertThat(review).extracting(FEEDBACK_FIELDS)
                .containsExactly("속도가 적절해요", "간투사가 줄었어요", "지난번보다 나아졌어요");
    }

    @DisplayName("빈 피드백은 기존 피드백을 지우지 않는다")
    @Test
    void applyFeedbackWithEmptyFeedback() {
        MeetingReview review = MeetingReview.of(ROOM_NAME, PROJECT_ID, MEMBER_ID);
        review.applyFeedback(SpeechFeedback.of("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요"));

        review.applyFeedback(SpeechFeedback.none());

        assertThat(review).extracting(FEEDBACK_FIELDS)
                .containsExactly("조금 빠릅니다", "간투사가 잦아요", "속도만 줄이면 좋겠어요");
    }

    private SpeechSegments segments() {
        return SpeechSegments.of(List.of(SpeechSegment.of(0.0, 3.0)));
    }
}
