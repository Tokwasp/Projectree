package ssafy.personal_audio_backend.domain.review.service;

import java.nio.file.Path;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.exception.CustomException;
import ssafy.personal_audio_backend.global.listener.sqs.RecordingCompletedMessage;

@Slf4j
@RequiredArgsConstructor
@Service
public class SpeechAnalysisService {

    private final FfmpegSilenceDetector silenceDetector;
    private final SilenceDetectOutputParser outputParser;
    private final SpeechFeedbackService speechFeedbackService;
    private final MeetingReviewAppender meetingReviewAppender;

    public void analyzeAndSave(RecordingCompletedMessage message, Path audioFile) {
        if (meetingReviewAppender.isAlreadyApplied(message)) {
            log.info("recording already applied. roomName={}, memberId={}, egressId={}", message.getRoomName(), message.getMemberId(), message.getEgressId());
            return;
        }

        SpeechSegments segments = outputParser.parse(silenceDetector.detect(audioFile));
        SpeechFeedback feedback = generateFeedbackQuietly(audioFile, segments);

        meetingReviewAppender.append(message, segments, feedback);
        logAnalyzed(message, segments, feedback);
    }

    private SpeechFeedback generateFeedbackQuietly(Path audioFile, SpeechSegments segments) {
        try {
            return speechFeedbackService.generate(audioFile, segments);
        } catch (CustomException e) {
            log.warn("ai feedback generation failed. file={}, errorCode={}", audioFile, e.getErrorCode());
            return SpeechFeedback.none();
        }
    }

    private void logAnalyzed(RecordingCompletedMessage message, SpeechSegments segments, SpeechFeedback feedback) {
        log.info("speech analyzed. roomName={}, memberId={}, speakingSeconds={}, segmentCount={}, "
                        + "longestSilenceSeconds={}, feedbackApplied={}",
                message.getRoomName(),
                message.getMemberId(),
                segments.speakingSeconds(),
                segments.segmentCount(),
                segments.longestSilenceSeconds(),
                !feedback.isEmpty());
    }
}
