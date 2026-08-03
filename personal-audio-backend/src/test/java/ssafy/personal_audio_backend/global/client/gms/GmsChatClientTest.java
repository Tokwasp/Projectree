package ssafy.personal_audio_backend.global.client.gms;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import ssafy.personal_audio_backend.global.exception.CustomException;

class GmsChatClientTest {

    private static final String BASE_URL = "https://gms.test";
    private static final String CHAT_URL = BASE_URL + "/v1/chat/completions";
    private static final String MODEL = "gpt-5.4-mini";
    private static final String SYSTEM_PROMPT = "너는 한국어 발표 코치다.";
    private static final String USER_TEXT = "분당 음절수: 300";

    private MockRestServiceServer server;
    private GmsChatClient gmsChatClient;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl(BASE_URL);
        server = MockRestServiceServer.bindTo(builder).build();
        gmsChatClient = new GmsChatClient(builder.build(), MODEL);
    }

    @DisplayName("시스템·유저 메시지를 실어 chat/completions 를 호출하고 본문을 돌려준다")
    @Test
    void completeJson() {
        String responseBody = """
                {
                  "choices": [
                    { "message": { "role": "assistant", "content": "{\\"speed\\":\\"조금 빠릅니다\\"}" } }
                  ]
                }
                """;
        server.expect(requestTo(CHAT_URL))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.model").value(MODEL))
                .andExpect(jsonPath("$.response_format.type").value("json_object"))
                .andExpect(jsonPath("$.messages[0].role").value("system"))
                .andExpect(jsonPath("$.messages[0].content").value(SYSTEM_PROMPT))
                .andExpect(jsonPath("$.messages[1].role").value("user"))
                .andExpect(jsonPath("$.messages[1].content").value(USER_TEXT))
                .andRespond(withSuccess(responseBody, MediaType.APPLICATION_JSON));

        String content = gmsChatClient.completeJson(SYSTEM_PROMPT, USER_TEXT);

        assertThat(content).isEqualTo("{\"speed\":\"조금 빠릅니다\"}");
        server.verify();
    }

    @DisplayName("오디오 파트를 보내지 않는다")
    @Test
    void completeJsonSendsTextOnly() {
        server.expect(requestTo(CHAT_URL))
                .andExpect(jsonPath("$.messages[1].content").isString())
                .andExpect(jsonPath("$.modalities").doesNotExist())
                .andRespond(withSuccess("""
                        {"choices":[{"message":{"content":"{}"}}]}
                        """, MediaType.APPLICATION_JSON));

        gmsChatClient.completeJson(SYSTEM_PROMPT, USER_TEXT);

        server.verify();
    }

    @DisplayName("GMS 가 오류를 반환하면 요청 실패 예외를 던진다")
    @Test
    void completeJsonWhenServerError() {
        server.expect(requestTo(CHAT_URL)).andRespond(withServerError());

        assertThatThrownBy(() -> gmsChatClient.completeJson(SYSTEM_PROMPT, USER_TEXT))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 요청에 실패했습니다.");
    }

    @DisplayName("응답에 선택지가 없으면 응답 해석 실패 예외를 던진다")
    @Test
    void completeJsonWhenNoChoices() {
        server.expect(requestTo(CHAT_URL))
                .andRespond(withSuccess("{\"choices\": []}", MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> gmsChatClient.completeJson(SYSTEM_PROMPT, USER_TEXT))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 응답을 해석하지 못했습니다.");
    }
}
