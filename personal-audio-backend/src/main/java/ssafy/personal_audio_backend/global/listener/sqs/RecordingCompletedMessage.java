package ssafy.personal_audio_backend.global.listener.sqs;

import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.ToString;

@Getter
@ToString
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RecordingCompletedMessage {

    private String roomName;
    private Long memberId;
    private String kind;
    private String objectKey;
    private String egressId;
    private LocalDateTime endedAt;
}
