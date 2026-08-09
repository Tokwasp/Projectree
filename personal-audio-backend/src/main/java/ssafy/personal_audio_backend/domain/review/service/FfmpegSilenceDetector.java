package ssafy.personal_audio_backend.domain.review.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import ssafy.personal_audio_backend.global.exception.CustomException;
import ssafy.personal_audio_backend.domain.review.service.exception.AudioErrorCode;

@Slf4j
@Component
public class FfmpegSilenceDetector {

    private static final String FFMPEG = "ffmpeg";
    private static final String LOG_FILE_PREFIX = "silencedetect-";
    private static final String LOG_FILE_SUFFIX = ".log";
    private static final int MILLIS_PER_SECOND = 1_000;
    private static final int SUCCESS_EXIT_CODE = 0;

    private final String silenceThreshold;
    private final Duration minSilenceDuration;
    private final Duration analyzeTimeout;

    public FfmpegSilenceDetector(
            @Value("${app.audio.silence-threshold}") String silenceThreshold,
            @Value("${app.audio.min-silence-duration}") Duration minSilenceDuration,
            @Value("${app.audio.analyze-timeout}") Duration analyzeTimeout) {
        this.silenceThreshold = silenceThreshold;
        this.minSilenceDuration = minSilenceDuration;
        this.analyzeTimeout = analyzeTimeout;
    }

    public String detect(Path audioFile) {
        Path logFile = createLogFile();
        try {
            return runFfmpeg(audioFile, logFile);
        } finally {
            deleteQuietly(logFile);
        }
    }

    private String runFfmpeg(Path audioFile, Path logFile) {
        Process process = startProcess(audioFile, logFile);
        try {
            awaitExit(process, audioFile);
            verifyExitCode(process, audioFile);

            return readOutput(logFile);
        } finally {
            process.destroyForcibly();
        }
    }

    private Process startProcess(Path audioFile, Path logFile) {
        ProcessBuilder processBuilder = new ProcessBuilder(
                FFMPEG,
                "-hide_banner",
                "-nostdin",
                "-i", audioFile.toString(),
                "-af", silenceDetectFilter(),
                "-f", "null",
                "-"
        );
        processBuilder.redirectErrorStream(true);
        processBuilder.redirectOutput(logFile.toFile());

        try {
            return processBuilder.start();
        } catch (IOException e) {
            log.warn("ffmpeg 실행에 실패했습니다. file={}, cause={}", audioFile, e.toString());
            throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
        }
    }

    private void awaitExit(Process process, Path audioFile) {
        try {
            if (process.waitFor(analyzeTimeout.toMillis(), TimeUnit.MILLISECONDS)) {
                return;
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
        }

        log.warn("ffmpeg 분석이 제한 시간을 넘겼습니다. file={}, timeout={}", audioFile, analyzeTimeout);
        throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_TIMEOUT);
    }

    private void verifyExitCode(Process process, Path audioFile) {
        int exitCode = process.exitValue();
        if (exitCode == SUCCESS_EXIT_CODE) {
            return;
        }

        log.warn("ffmpeg 가 비정상 종료했습니다. file={}, exitCode={}", audioFile, exitCode);
        throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
    }

    private String readOutput(Path logFile) {
        try {
            return Files.readString(logFile);
        } catch (IOException e) {
            log.warn("ffmpeg 출력을 읽지 못했습니다. path={}, cause={}", logFile, e.toString());
            throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
        }
    }

    private String silenceDetectFilter() {
        double minSilenceSeconds = (double) minSilenceDuration.toMillis() / MILLIS_PER_SECOND;
        return "silencedetect=noise=%s:d=%s".formatted(silenceThreshold, minSilenceSeconds);
    }

    private Path createLogFile() {
        try {
            return Files.createTempFile(LOG_FILE_PREFIX, LOG_FILE_SUFFIX);
        } catch (IOException e) {
            log.warn("ffmpeg 로그 임시파일을 만들지 못했습니다. cause={}", e.toString());
            throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
        }
    }

    private void deleteQuietly(Path file) {
        try {
            Files.deleteIfExists(file);
        } catch (IOException e) {
            log.warn("ffmpeg 로그 임시파일을 지우지 못했습니다. path={}", file, e);
        }
    }
}
