package ssafy.personal_audio_backend.global.client.gms;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import ssafy.personal_audio_backend.global.exception.CustomException;

class GmsTranscriptionClientTest {

    private static final String BASE_URL = "https://gms.test";
    private static final String TRANSCRIBE_URL = BASE_URL + "/v1/audio/transcriptions";
    private static final String MODEL = "whisper-1";
    private static final String STYLE_PROMPT = "어… 음… 그…";
    private static final long MAX_UPLOAD_BYTES = 100L;

    @TempDir
    private Path tempDir;

    private MockRestServiceServer server;
    private GmsTranscriptionClient gmsTranscriptionClient;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl(BASE_URL);
        server = MockRestServiceServer.bindTo(builder).build();
        gmsTranscriptionClient = new GmsTranscriptionClient(builder.build(), MODEL, MAX_UPLOAD_BYTES);
    }

    @DisplayName("녹음 파일과 옵션을 multipart 로 보내고 대본을 돌려준다")
    @Test
    void transcribe() throws IOException {
        String responseBody = """
                {
                  "text": "어 안녕하세요",
                  "language": "korean",
                  "duration": 8.9,
                  "segments": [
                    {"start": 0.0, "end": 4.0, "text": "어 안녕하세요",
                     "avg_logprob": -0.5, "no_speech_prob": 0.01}
                  ]
                }
                """;
        server.expect(requestTo(TRANSCRIBE_URL))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentTypeCompatibleWith(MediaType.MULTIPART_FORM_DATA))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"model\"")))
                .andExpect(content().string(org.hamcrest.Matchers.containsString(MODEL)))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("verbose_json")))
                .andRespond(withSuccess(responseBody, MediaType.APPLICATION_JSON));

        GmsTranscription transcription = gmsTranscriptionClient.transcribe(audioFile(10), STYLE_PROMPT);

        assertThat(transcription.getText()).isEqualTo("어 안녕하세요");
        assertThat(transcription.segmentCount()).isEqualTo(1);
        assertThat(transcription.averageLogprob()).isEqualTo(-0.5);
        server.verify();
    }

    @DisplayName("업로드 상한을 넘는 파일은 호출하지 않고 막는다")
    @Test
    void transcribeWhenAudioTooLarge() throws IOException {
        Path tooLarge = audioFile((int) MAX_UPLOAD_BYTES + 1);

        assertThatThrownBy(() -> gmsTranscriptionClient.transcribe(tooLarge, STYLE_PROMPT))
                .isInstanceOf(CustomException.class)
                .hasMessage("음성 파일이 너무 커서 분석할 수 없습니다.");

        server.verify();
    }

    @DisplayName("대본이 비어 있으면 응답 해석 실패 예외를 던진다")
    @Test
    void transcribeWhenTextIsBlank() throws IOException {
        server.expect(requestTo(TRANSCRIBE_URL))
                .andRespond(withSuccess("{\"text\": \"\"}", MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> gmsTranscriptionClient.transcribe(audioFile(10), STYLE_PROMPT))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 응답을 해석하지 못했습니다.");
    }

    @DisplayName("GMS 가 오류를 반환하면 요청 실패 예외를 던진다")
    @Test
    void transcribeWhenBadRequest() throws IOException {
        server.expect(requestTo(TRANSCRIBE_URL))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST));

        assertThatThrownBy(() -> gmsTranscriptionClient.transcribe(audioFile(10), STYLE_PROMPT))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 요청에 실패했습니다.");
    }

    private Path audioFile(int size) throws IOException {
        return Files.write(tempDir.resolve("recording-%d.ogg".formatted(size)), new byte[size]);
    }
}
