package ssafy.personal_audio_backend.repository;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import ssafy.personal_audio_backend.domain.review.MeetingReview;

public interface MeetingReviewRepository extends JpaRepository<MeetingReview, Integer> {

    Optional<MeetingReview> findByRoomNameAndMemberId(String roomName, int memberId);
}
