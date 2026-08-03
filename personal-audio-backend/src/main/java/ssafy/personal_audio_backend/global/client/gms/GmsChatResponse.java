package ssafy.personal_audio_backend.global.client.gms;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * OpenAI 호환 chat/completions 응답 본문. 첫 번째 선택지의 본문만 쓴다.
 */
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@JsonIgnoreProperties(ignoreUnknown = true)
class GmsChatResponse {

    private List<Choice> choices;

    String firstContent() {
        if (choices == null || choices.isEmpty()) {
            return null;
        }

        Choice choice = choices.getFirst();
        if (choice == null || choice.getMessage() == null) {
            return null;
        }

        return choice.getMessage().getContent();
    }

    @Getter
    @NoArgsConstructor(access = AccessLevel.PROTECTED)
    @JsonIgnoreProperties(ignoreUnknown = true)
    static class Choice {

        private Message message;
    }

    @Getter
    @NoArgsConstructor(access = AccessLevel.PROTECTED)
    @JsonIgnoreProperties(ignoreUnknown = true)
    static class Message {

        private String content;
    }
}
