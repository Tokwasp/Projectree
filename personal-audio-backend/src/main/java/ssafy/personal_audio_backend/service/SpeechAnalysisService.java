package ssafy.personal_audio_backend.service;

import java.nio.file.Path;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ssafy.personal_audio_backend.domain.review.MeetingReview;
import ssafy.personal_audio_backend.domain.speech.SpeechSegments;
import ssafy.personal_audio_backend.listener.sqs.RecordingCompletedMessage;
import ssafy.personal_audio_backend.repository.MeetingReviewRepository;

@Slf4j
@Transactional
@RequiredArgsConstructor
@Service
public class SpeechAnalysisService {

    private final FfmpegSilenceDetector silenceDetector;
    private final SilenceDetectOutputParser outputParser;
    private final MeetingReviewRepository meetingReviewRepository;

    public void analyzeAndSave(RecordingCompletedMessage message, Path audioFile) {
        SpeechSegments segments = outputParser.parse(silenceDetector.detect(audioFile));
        int memberId = Math.toIntExact(message.getMemberId());

        MeetingReview review = meetingReviewRepository.findByRoomNameAndMemberId(message.getRoomName(), memberId)
                .orElseGet(() -> MeetingReview.of(message.getRoomName(), memberId));

        if (review.isAlreadyApplied(message.getEgressId())) {
            log.info("이미 반영한 녹음입니다. roomName={}, memberId={}, egressId={}", message.getRoomName(), memberId, message.getEgressId());
            return;
        }

        review.add(segments, message.getEgressId());
        meetingReviewRepository.save(review);
        logAnalyzed(message, segments);
    }

    private void logAnalyzed(RecordingCompletedMessage message, SpeechSegments segments) {
        log.info("speech analyzed. roomName={}, memberId={}, speakingSeconds={}, segmentCount={}, longestSilenceSeconds={}",
                message.getRoomName(),
                message.getMemberId(),
                segments.speakingSeconds(),
                segments.segmentCount(),
                segments.longestSilenceSeconds());
    }
}
