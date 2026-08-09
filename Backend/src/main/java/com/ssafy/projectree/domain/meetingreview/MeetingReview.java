package com.ssafy.projectree.domain.meetingreview;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

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

    @Builder
    private MeetingReview(String roomName, int projectId, int memberId, int speakingSeconds,
                           String speedFeedback, String personalFeedback, String overallFeedback) {
        this.roomName = roomName;
        this.projectId = projectId;
        this.memberId = memberId;
        this.speakingSeconds = speakingSeconds;
        this.speedFeedback = speedFeedback;
        this.personalFeedback = personalFeedback;
        this.overallFeedback = overallFeedback;
    }

    public static MeetingReview of(String roomName, int projectId, int memberId, int speakingSeconds,
                                    String speedFeedback, String personalFeedback, String overallFeedback) {
        return MeetingReview.builder()
                .roomName(roomName)
                .projectId(projectId)
                .memberId(memberId)
                .speakingSeconds(speakingSeconds)
                .speedFeedback(speedFeedback)
                .personalFeedback(personalFeedback)
                .overallFeedback(overallFeedback)
                .build();
    }

}
