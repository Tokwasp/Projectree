package ssafy.personal_audio_backend.listener.sqs;

import io.awspring.cloud.sqs.annotation.SqsListener;
import java.nio.file.Path;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import ssafy.personal_audio_backend.service.RecordingFileService;

@Slf4j
@Component
@RequiredArgsConstructor
public class RecordingCompletedListener {

    private final RecordingFileService recordingFileService;

    @SqsListener("${app.sqs.queue-name}")
    public void handle(RecordingCompletedMessage message) {
        log.info("recording completed. roomName={}, memberId={}, kind={}, objectKey={}, egressId={}, endedAt={}",
                message.getRoomName(),
                message.getMemberId(),
                message.getKind(),
                message.getObjectKey(),
                message.getEgressId(),
                message.getEndedAt());

        Path audioFile = recordingFileService.downloadToTempFile(message.getObjectKey());
        try {
            log.info("audio ready. memberId={}, path={}", message.getMemberId(), audioFile);
        } finally {
            recordingFileService.delete(audioFile);
        }
    }
}
