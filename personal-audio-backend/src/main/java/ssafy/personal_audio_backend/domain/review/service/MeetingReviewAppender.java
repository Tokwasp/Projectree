package ssafy.personal_audio_backend.domain.review.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ssafy.personal_audio_backend.domain.review.MeetingReview;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.repository.MeetingReviewRepository;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.listener.sqs.RecordingCompletedMessage;

@Slf4j
@RequiredArgsConstructor
@Service
public class MeetingReviewAppender {

    private final MeetingReviewRepository meetingReviewRepository;

    @Transactional(readOnly = true)
    public boolean isAlreadyApplied(RecordingCompletedMessage message) {
        return meetingReviewRepository
                .findByRoomNameAndMemberId(message.getRoomName(), memberIdOf(message))
                .filter(review -> review.isAlreadyApplied(message.getEgressId()))
                .isPresent();
    }

    @Transactional
    public void append(RecordingCompletedMessage message, SpeechSegments segments, SpeechFeedback feedback) {
        int memberId = memberIdOf(message);

        MeetingReview review = meetingReviewRepository.findByRoomNameAndMemberId(message.getRoomName(), memberId)
                .orElseGet(() -> MeetingReview.of(message.getRoomName(), memberId));

        if (review.isAlreadyApplied(message.getEgressId())) {
            log.info("recording already applied. roomName={}, memberId={}, egressId={}",
                    message.getRoomName(), memberId, message.getEgressId());
            return;
        }

        review.add(segments, message.getEgressId());
        review.applyFeedback(feedback);
        meetingReviewRepository.save(review);
    }

    private int memberIdOf(RecordingCompletedMessage message) {
        return Math.toIntExact(message.getMemberId());
    }
}
