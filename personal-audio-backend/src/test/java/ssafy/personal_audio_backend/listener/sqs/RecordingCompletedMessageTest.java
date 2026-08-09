package ssafy.personal_audio_backend.listener.sqs;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDateTime;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import ssafy.personal_audio_backend.global.listener.sqs.RecordingCompletedMessage;
import tools.jackson.databind.json.JsonMapper;

class RecordingCompletedMessageTest {

    private final JsonMapper jsonMapper = JsonMapper.builder().build();

    @DisplayName("큐에서 받은 JSON을 메시지 객체로 역직렬화한다")
    @Test
    void deserialize() {
        String payload = """
                {
                  "roomName": "efb9541a-97fc-4647-9de2-80873b708c0c",
                  "projectId": 5,
                  "memberId": 7,
                  "kind": "PARTICIPANT",
                  "objectKey": "meetings/efb9541a-97fc-4647-9de2-80873b708c0c/7/2026-08-01T052705.ogg",
                  "egressId": "EG_YEMSyA8vLjac",
                  "endedAt": "2026-08-01T05:27:32.553029501"
                }
                """;

        RecordingCompletedMessage message = jsonMapper.readValue(payload, RecordingCompletedMessage.class);

        assertThat(message.getRoomName()).isEqualTo("efb9541a-97fc-4647-9de2-80873b708c0c");
        assertThat(message.getProjectId()).isEqualTo(5L);
        assertThat(message.getMemberId()).isEqualTo(7L);
        assertThat(message.getKind()).isEqualTo("PARTICIPANT");
        assertThat(message.getObjectKey())
                .isEqualTo("meetings/efb9541a-97fc-4647-9de2-80873b708c0c/7/2026-08-01T052705.ogg");
        assertThat(message.getEgressId()).isEqualTo("EG_YEMSyA8vLjac");
        assertThat(message.getEndedAt())
                .isEqualTo(LocalDateTime.of(2026, 8, 1, 5, 27, 32, 553029501));
    }
}
