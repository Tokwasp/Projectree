package ssafy.personal_audio_backend.domain.review.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegment;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.client.gms.GmsChatClient;
import ssafy.personal_audio_backend.global.client.gms.GmsTranscription;
import ssafy.personal_audio_backend.global.client.gms.GmsTranscriptionClient;
import ssafy.personal_audio_backend.global.client.gms.exception.GmsErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;
import tools.jackson.databind.json.JsonMapper;

@ExtendWith(MockitoExtension.class)
class SpeechFeedbackServiceTest {

    private static final Path AUDIO_FILE = Path.of("recording.ogg");
    private static final Path COMPRESSED_FILE = Path.of("recording.mp3");
    private static final String FEEDBACK_JSON = """
            {"speed":"조금 빠릅니다","personal":"간투사가 잦아요","overall":"속도만 줄이면 좋겠어요"}
            """;

    @Mock
    private GmsTranscriptionClient gmsTranscriptionClient;

    @Mock
    private GmsChatClient gmsChatClient;

    @Mock
    private FfmpegAudioConverter audioConverter;

    @Mock
    private RecordingFileService recordingFileService;

    @Captor
    private ArgumentCaptor<String> userMessageCaptor;

    private final JsonMapper jsonMapper = JsonMapper.builder().build();

    private SpeechFeedbackService speechFeedbackService;

    @BeforeEach
    void setUp() {
        speechFeedbackService = new SpeechFeedbackService(
                gmsTranscriptionClient, gmsChatClient, audioConverter, recordingFileService, jsonMapper);
    }

    @DisplayName("대본을 받아 피드백 세 줄을 만든다")
    @Test
    void generate() {
        givenTranscript("안녕하세요 반갑습니다");
        givenChatReturns(FEEDBACK_JSON);

        SpeechFeedback feedback = speechFeedbackService.generate(AUDIO_FILE, segments(10.0));

        assertThat(feedback.speed()).isEqualTo("조금 빠릅니다");
        assertThat(feedback.personal()).isEqualTo("간투사가 잦아요");
        assertThat(feedback.overall()).isEqualTo("속도만 줄이면 좋겠어요");
    }

    @DisplayName("서버가 계산한 분당 음절수와 간투사 집계를 AI 에 넘긴다")
    @Test
    void generatePassesComputedNumbers() {
        givenTranscript("어 어 안녕하세요 반갑습니다");
        givenChatReturns(FEEDBACK_JSON);

        speechFeedbackService.generate(AUDIO_FILE, segments(10.0));

        verify(gmsChatClient).completeJson(anyString(), userMessageCaptor.capture());
        assertThat(userMessageCaptor.getValue())
                .contains("분당 음절수: 72")
                .contains("간투사(명확): 2회 — 어×2")
                .contains("발화 시간: 10초");
    }

    @DisplayName("발화 시간을 모르면 속도를 측정 불가로 넘긴다")
    @Test
    void generateWithoutSpeakingTime() {
        givenTranscript("안녕하세요");
        givenChatReturns(FEEDBACK_JSON);

        speechFeedbackService.generate(AUDIO_FILE, SpeechSegments.of(List.of()));

        verify(gmsChatClient).completeJson(anyString(), userMessageCaptor.capture());
        assertThat(userMessageCaptor.getValue()).contains("분당 음절수: 측정 불가");
    }

    @DisplayName("코드블록으로 감싸 온 JSON 도 해석한다")
    @Test
    void generateWithCodeFencedJson() {
        givenTranscript("안녕하세요");
        givenChatReturns("```json\n" + FEEDBACK_JSON + "```");

        SpeechFeedback feedback = speechFeedbackService.generate(AUDIO_FILE, segments(10.0));

        assertThat(feedback.speed()).isEqualTo("조금 빠릅니다");
    }

    @DisplayName("JSON 이 아니면 응답 해석 실패 예외를 던진다")
    @Test
    void generateWithBrokenJson() {
        givenTranscript("안녕하세요");
        givenChatReturns("조금 빠르게 말하고 있어요");

        assertThatThrownBy(() -> speechFeedbackService.generate(AUDIO_FILE, segments(10.0)))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 응답을 해석하지 못했습니다.");
    }

    @DisplayName("파일이 업로드 상한을 넘으면 압축해 한 번 더 시도한다")
    @Test
    void generateRetriesWithCompressedAudio() {
        given(gmsTranscriptionClient.transcribe(eq(AUDIO_FILE), anyString()))
                .willThrow(new CustomException(GmsErrorCode.GMS_AUDIO_TOO_LARGE));
        given(audioConverter.toMp3(AUDIO_FILE)).willReturn(COMPRESSED_FILE);
        given(gmsTranscriptionClient.transcribe(eq(COMPRESSED_FILE), anyString()))
                .willReturn(transcriptionOf("안녕하세요"));
        givenChatReturns(FEEDBACK_JSON);

        SpeechFeedback feedback = speechFeedbackService.generate(AUDIO_FILE, segments(10.0));

        assertThat(feedback.speed()).isEqualTo("조금 빠릅니다");
        verify(recordingFileService).delete(COMPRESSED_FILE);
    }

    @DisplayName("업로드 상한 외의 STT 실패는 압축하지 않고 그대로 던진다")
    @Test
    void generateDoesNotRetryOnOtherFailures() {
        given(gmsTranscriptionClient.transcribe(eq(AUDIO_FILE), anyString()))
                .willThrow(new CustomException(GmsErrorCode.GMS_TIMEOUT));

        assertThatThrownBy(() -> speechFeedbackService.generate(AUDIO_FILE, segments(10.0)))
                .isInstanceOf(CustomException.class)
                .hasMessage("AI 피드백 요청이 제한 시간을 넘었습니다.");
    }

    private void givenTranscript(String text) {
        given(gmsTranscriptionClient.transcribe(any(Path.class), anyString()))
                .willReturn(transcriptionOf(text));
    }

    private void givenChatReturns(String content) {
        given(gmsChatClient.completeJson(anyString(), anyString())).willReturn(content);
    }

    private GmsTranscription transcriptionOf(String text) {
        return jsonMapper.readValue("""
                {"text":"%s","language":"korean","duration":10.0,"segments":[]}
                """.formatted(text), GmsTranscription.class);
    }

    private SpeechSegments segments(double endSeconds) {
        return SpeechSegments.of(List.of(SpeechSegment.of(0.0, endSeconds)));
    }
}
