package ssafy.personal_audio_backend.domain.review.service;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import ssafy.personal_audio_backend.domain.review.feedback.FillerWords;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechFeedback;
import ssafy.personal_audio_backend.domain.review.feedback.SpeechTranscript;
import ssafy.personal_audio_backend.domain.review.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.client.gms.GmsChatClient;
import ssafy.personal_audio_backend.global.client.gms.GmsTranscription;
import ssafy.personal_audio_backend.global.client.gms.GmsTranscriptionClient;
import ssafy.personal_audio_backend.global.client.gms.exception.GmsErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * 녹음을 대본으로 바꾼 뒤, 서버가 계산한 수치와 함께 AI 에 넘겨 말하기 피드백을 받는다.
 * <p>
 * 속도와 간투사는 서버가 세어 수치로 넘기고 AI 는 문구만 만든다. AI 가 숫자를 추측하지 않게 하려는 것이다.
 * 수십 초가 걸리는 외부 호출이 두 번 일어나므로 트랜잭션 안에서 실행하지 않는다.
 */
@Slf4j
@RequiredArgsConstructor
@Service
public class SpeechFeedbackService {

    private static final String SYSTEM_PROMPT = """
            너는 발표를 도와주는 따뜻한 한국어 말하기 코치다.
            주어진 수치와 대본을 보고 세 항목에 대해 사람에게 건네는 말로 피드백한다.

            [말투]
            - 존댓말로, 상대를 존중하고 격려하는 말투로 쓴다.
            - 잘하고 있는 점은 분명하게 칭찬한다. 고칠 점이 없으면 칭찬만 해도 된다.
            - 고칠 점은 단정하지 말고 "~할 수도 있어요", "~해보시면 좋겠어요"처럼 부드럽게 제안한다.
            - "느립니다", "부족합니다"처럼 판정하듯 끊는 말투는 쓰지 않는다.
            - 느낌표와 문장 부호는 자연스러우면 써도 된다. 따옴표와 줄바꿈은 넣지 않는다.

            [항목]
            speed: 말하기 속도. 분당 음절수만 근거로 삼는다. 20~25자.
            personal: 간투사 사용 습관. 간투사 집계만 근거로 삼는다. 20~25자.
            overall: 앞의 두 항목을 아우르며 격려로 마무리하는 한 줄. 30~40자.

            길이는 화면에 들어가야 하므로 반드시 지킨다. 짧아도 따뜻하게 쓸 수 있다.

            [지켜야 할 것]
            - 주지 않은 정보는 추측하지 않는다. 근거는 분당 음절수와 간투사 집계, 대본 내용뿐이다.
            - 음성을 듣지 않았으므로 발음·목소리·억양·성량은 언급하지 않는다.
              "또렷하다", "명료하다", "발음이 좋다", "목소리가 좋다" 같은 표현을 쓰지 않는다.
            - overall 은 앞 두 문장을 그대로 나열하지 말고, 무엇이 좋았는지 한 가지를 짚어 격려한다.

            [좋은 예]
            {"speed":"조금 느리지만 편안하게 들려요",\
            "personal":"간투사가 거의 없어 듣기 편해요!",\
            "overall":"차분하고 듣는 사람을 배려하는 말투예요. 좋습니다!"}
            {"speed":"조금 빠르니 한 박자 쉬어가도 좋아요",\
            "personal":"'음'이 잦은 편이라 조금만 줄여보세요",\
            "overall":"전달이 분명해요. 속도만 늦추면 훨씬 좋아지겠어요!"}

            [나쁜 예 — 성의 없어 보이므로 이렇게 쓰지 않는다]
            {"speed":"느립니다","personal":"간투사가 없습니다","overall":"속도는 느리고 간투사도 없습니다"}

            아래 JSON만 출력한다.
            {"speed":"","personal":"","overall":""}
            """;

    private static final String USER_MESSAGE = """
            분당 음절수: %s
            발화 시간: %d초, 발화 구간 %d개, 최장 침묵 %d초
            간투사(명확): %s
            간투사(문맥의존, 정상적인 쓰임이 섞일 수 있음): %s

            대본:
            %s
            """;

    private static final String SPEED_GUIDE = "%d (느림 250 미만 / 보통 250~350 / 빠름 350 초과)";
    private static final String SPEED_UNKNOWN = "측정 불가 (발화 시간을 알 수 없음)";
    private static final String NO_FILLER = "0회";
    private static final String CODE_FENCE = "```";
    private static final int UNKNOWN_SPEED = 0;

    private final GmsTranscriptionClient gmsTranscriptionClient;
    private final GmsChatClient gmsChatClient;
    private final FfmpegAudioConverter audioConverter;
    private final RecordingFileService recordingFileService;
    private final ObjectMapper objectMapper;

    public SpeechFeedback generate(Path audioFile, SpeechSegments segments) {
        SpeechTranscript transcript = SpeechTranscript.of(transcribe(audioFile).getText());

        return parse(gmsChatClient.completeJson(SYSTEM_PROMPT, userMessageOf(transcript, segments)));
    }

    private GmsTranscription transcribe(Path audioFile) {
        try {
            return gmsTranscriptionClient.transcribe(audioFile, FillerWords.transcriptionHint());
        } catch (CustomException e) {
            if (e.getErrorCode() != GmsErrorCode.GMS_AUDIO_TOO_LARGE) {
                throw e;
            }

            return transcribeCompressed(audioFile);
        }
    }

    /**
     * 업로드 상한을 넘긴 녹음은 모노 16kHz mp3 로 줄여 한 번만 다시 시도한다.
     */
    private GmsTranscription transcribeCompressed(Path audioFile) {
        log.info("audio exceeds upload limit. compressing before retry. file={}", audioFile);

        Path compressed = audioConverter.toMp3(audioFile);
        try {
            return gmsTranscriptionClient.transcribe(compressed, FillerWords.transcriptionHint());
        } finally {
            recordingFileService.delete(compressed);
        }
    }

    private String userMessageOf(SpeechTranscript transcript, SpeechSegments segments) {
        return USER_MESSAGE.formatted(
                speedOf(transcript, segments),
                segments.speakingSeconds(),
                segments.segmentCount(),
                segments.longestSilenceSeconds(),
                tallyOf(FillerWords.tallyClear(transcript.text())),
                tallyOf(FillerWords.tallyAmbiguous(transcript.text())),
                transcript.text());
    }

    private String speedOf(SpeechTranscript transcript, SpeechSegments segments) {
        int syllablesPerMinute = transcript.syllablesPerMinute(segments.speakingSeconds());
        if (syllablesPerMinute == UNKNOWN_SPEED) {
            return SPEED_UNKNOWN;
        }

        return SPEED_GUIDE.formatted(syllablesPerMinute);
    }

    private String tallyOf(Map<String, Long> tally) {
        if (tally.isEmpty()) {
            return NO_FILLER;
        }

        long total = tally.values().stream().mapToLong(Long::longValue).sum();

        return tally.entrySet().stream()
                .map(entry -> "%s×%d".formatted(entry.getKey(), entry.getValue()))
                .collect(Collectors.joining(", ", "%d회 — ".formatted(total), ""));
    }

    private SpeechFeedback parse(String content) {
        try {
            FeedbackPayload payload = objectMapper.readValue(stripCodeFence(content), FeedbackPayload.class);

            return SpeechFeedback.of(payload.getSpeed(), payload.getPersonal(), payload.getOverall());
        } catch (JacksonException e) {
            log.warn("failed to parse gms feedback json. cause={}", e.getMessage());
            throw new CustomException(GmsErrorCode.GMS_RESPONSE_INVALID);
        }
    }

    /**
     * response_format 을 무시하고 ```json 블록으로 감싸 오는 모델이 있어 벗겨낸다.
     */
    private String stripCodeFence(String content) {
        String trimmed = content.trim();
        if (!trimmed.startsWith(CODE_FENCE)) {
            return trimmed;
        }

        int bodyStart = trimmed.indexOf('\n');
        int bodyEnd = trimmed.lastIndexOf(CODE_FENCE);
        if (bodyStart < 0 || bodyEnd <= bodyStart) {
            return trimmed;
        }

        return trimmed.substring(bodyStart + 1, bodyEnd).trim();
    }

    @Getter
    @NoArgsConstructor(access = AccessLevel.PROTECTED)
    @JsonIgnoreProperties(ignoreUnknown = true)
    static class FeedbackPayload {

        private String speed;
        private String personal;
        private String overall;
    }
}
