package ssafy.personal_audio_backend.global.client.gms;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.Getter;

/**
 * OpenAI 호환 chat/completions 요청 본문. 텍스트만 주고받는다.
 */
@Getter
class GmsChatRequest {

    private final String model;

    @JsonProperty("response_format")
    private final ResponseFormat responseFormat;

    private final List<Message> messages;

    private GmsChatRequest(String model, ResponseFormat responseFormat, List<Message> messages) {
        this.model = model;
        this.responseFormat = responseFormat;
        this.messages = messages;
    }

    static GmsChatRequest jsonAnswer(String model, String systemPrompt, String userText) {
        List<Message> messages = List.of(
                Message.system(systemPrompt),
                Message.user(userText)
        );

        return new GmsChatRequest(model, ResponseFormat.jsonObject(), messages);
    }

    @Getter
    static class ResponseFormat {

        private static final String JSON_OBJECT = "json_object";

        private final String type;

        private ResponseFormat(String type) {
            this.type = type;
        }

        static ResponseFormat jsonObject() {
            return new ResponseFormat(JSON_OBJECT);
        }
    }

    @Getter
    static class Message {

        private static final String ROLE_SYSTEM = "system";
        private static final String ROLE_USER = "user";

        private final String role;
        private final String content;

        private Message(String role, String content) {
            this.role = role;
            this.content = content;
        }

        static Message system(String content) {
            return new Message(ROLE_SYSTEM, content);
        }

        static Message user(String content) {
            return new Message(ROLE_USER, content);
        }
    }
}
