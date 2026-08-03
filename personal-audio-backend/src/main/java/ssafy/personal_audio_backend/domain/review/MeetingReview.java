package ssafy.personal_audio_backend.domain.review;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.Objects;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import ssafy.personal_audio_backend.domain.BaseEntity;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;

@Getter
@Entity
@Table(
        name = "meeting_review",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_review_room_member",
                columnNames = {"room_name", "member_id"}
        ),
        indexes = {
                @Index(
                        name = "idx_meeting_review_member_created",
                        columnList = "member_id, created_at"
                ),
                @Index(
                        name = "idx_meeting_review_project_member",
                        columnList = "project_id, member_id"
                )
        }
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingReview extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "room_name", nullable = false, length = 100)
    private String roomName;

    @Column(name = "project_id", nullable = false)
    private int projectId;

    @Column(name = "member_id", nullable = false)
    private int memberId;

    @Column(name = "speaking_seconds", nullable = false)
    private int speakingSeconds;

    @Column(name = "last_egress_id", length = 100)
    private String lastEgressId;

    @Column(name = "speed_feedback", length = 100)
    private String speedFeedback;

    @Column(name = "personal_feedback", length = 100)
    private String personalFeedback;

    @Column(name = "overall_feedback", length = 100)
    private String overallFeedback;

    private MeetingReview(String roomName, int projectId, int memberId) {
        this.roomName = roomName;
        this.projectId = projectId;
        this.memberId = memberId;
    }

    public static MeetingReview of(String roomName, int projectId, int memberId) {
        return new MeetingReview(roomName, projectId, memberId);
    }

    public boolean isAlreadyApplied(String egressId) {
        return Objects.equals(this.lastEgressId, egressId);
    }

    public void add(SpeechSegments segments, String egressId) {
        this.speakingSeconds += segments.speakingSeconds();
        this.lastEgressId = egressId;
    }

    public void applyFeedback(SpeechFeedback feedback) {
        if (feedback.isEmpty()) {
            return;
        }

        this.speedFeedback = feedback.speed();
        this.personalFeedback = feedback.personal();
        this.overallFeedback = feedback.overall();
    }
}
