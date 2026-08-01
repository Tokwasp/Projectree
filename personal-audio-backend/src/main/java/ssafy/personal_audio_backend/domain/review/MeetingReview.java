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
import ssafy.personal_audio_backend.domain.speech.SpeechSegments;

@Getter
@Entity
@Table(
        name = "meeting_review",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_meeting_review_room_member",
                columnNames = {"room_name", "member_id"}
        ),
        indexes = @Index(
                name = "idx_meeting_review_member_created",
                columnList = "member_id, created_at"
        )
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingReview extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "room_name", nullable = false, length = 100)
    private String roomName;

    @Column(name = "member_id", nullable = false)
    private int memberId;

    @Column(name = "speaking_seconds", nullable = false)
    private int speakingSeconds;

    @Column(name = "segment_count", nullable = false)
    private int segmentCount;

    @Column(name = "longest_silence_seconds", nullable = false)
    private int longestSilenceSeconds;

    @Column(name = "last_egress_id", length = 100)
    private String lastEgressId;

    private MeetingReview(String roomName, int memberId) {
        this.roomName = roomName;
        this.memberId = memberId;
    }

    public static MeetingReview of(String roomName, int memberId) {
        return new MeetingReview(roomName, memberId);
    }

    public boolean isAlreadyApplied(String egressId) {
        return Objects.equals(this.lastEgressId, egressId);
    }

    public void add(SpeechSegments segments, String egressId) {
        this.speakingSeconds += segments.speakingSeconds();
        this.segmentCount += segments.segmentCount();
        this.longestSilenceSeconds = Math.max(this.longestSilenceSeconds, segments.longestSilenceSeconds());
        this.lastEgressId = egressId;
    }
}
