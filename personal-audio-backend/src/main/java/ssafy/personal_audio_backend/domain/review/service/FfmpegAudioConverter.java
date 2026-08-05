package ssafy.personal_audio_backend.domain.review.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import ssafy.personal_audio_backend.domain.review.service.exception.AudioErrorCode;
import ssafy.personal_audio_backend.global.exception.CustomException;

@Slf4j
@Component
public class FfmpegAudioConverter {

    private static final String FFMPEG = "ffmpeg";
    private static final String OUTPUT_FILE_PREFIX = "recording-mp3-";
    private static final String OUTPUT_FILE_SUFFIX = ".mp3";
    private static final String LOG_FILE_PREFIX = "ffmpeg-convert-";
    private static final String LOG_FILE_SUFFIX = ".log";
    private static final int SUCCESS_EXIT_CODE = 0;
    private static final int ERROR_LOG_LIMIT = 500;

    private static final String CHANNELS = "1";
    private static final String SAMPLE_RATE = "16000";
    private static final String BITRATE = "64k";

    private final long maxSeconds;
    private final Duration convertTimeout;

    public FfmpegAudioConverter(
            @Value("${app.ai.audio.max-seconds}") long maxSeconds,
            @Value("${app.ai.audio.convert-timeout}") Duration convertTimeout) {
        this.maxSeconds = maxSeconds;
        this.convertTimeout = convertTimeout;
    }

    public Path toMp3(Path source) {
        Path target = createOutputFile();
        try {
            convert(source, target);

            return target;
        } catch (RuntimeException e) {
            deleteQuietly(target);
            throw e;
        }
    }

    private void convert(Path source, Path target) {
        Path logFile = createLogFile();
        try {
            runFfmpeg(source, target, logFile);
        } finally {
            deleteQuietly(logFile);
        }
    }

    private void runFfmpeg(Path source, Path target, Path logFile) {
        Process process = startProcess(source, target, logFile);
        try {
            awaitExit(process, source);
            verifyExitCode(process, source, logFile);
        } finally {
            process.destroyForcibly();
        }
    }

    private Process startProcess(Path source, Path target, Path logFile) {
        ProcessBuilder processBuilder = new ProcessBuilder(
                FFMPEG,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i", source.toString(),
                "-vn",
                "-ac", CHANNELS,
                "-ar", SAMPLE_RATE,
                "-b:a", BITRATE,
                "-t", String.valueOf(maxSeconds),
                target.toString()
        );
        processBuilder.redirectErrorStream(true);
        processBuilder.redirectOutput(logFile.toFile());

        try {
            return processBuilder.start();
        } catch (IOException e) {
            log.warn("ffmpeg 실행에 실패했습니다. file={}, cause={}", source, e.toString());
            throw new CustomException(AudioErrorCode.AUDIO_CONVERT_FAILED);
        }
    }

    private void awaitExit(Process process, Path source) {
        try {
            if (process.waitFor(convertTimeout.toMillis(), TimeUnit.MILLISECONDS)) {
                return;
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new CustomException(AudioErrorCode.AUDIO_CONVERT_FAILED);
        }

        log.warn("ffmpeg 변환이 제한 시간을 넘겼습니다. file={}, timeout={}", source, convertTimeout);
        throw new CustomException(AudioErrorCode.AUDIO_CONVERT_TIMEOUT);
    }

    private void verifyExitCode(Process process, Path source, Path logFile) {
        int exitCode = process.exitValue();
        if (exitCode == SUCCESS_EXIT_CODE) {
            return;
        }

        log.warn("ffmpeg 변환이 비정상 종료했습니다. file={}, exitCode={}, output={}",
                source, exitCode, tailOf(logFile));
        throw new CustomException(AudioErrorCode.AUDIO_CONVERT_FAILED);
    }

    private String tailOf(Path logFile) {
        try {
            String output = Files.readString(logFile);
            if (output.length() <= ERROR_LOG_LIMIT) {
                return output;
            }

            return output.substring(output.length() - ERROR_LOG_LIMIT);
        } catch (IOException e) {
            return "";
        }
    }

    private Path createOutputFile() {
        try {
            return Files.createTempFile(OUTPUT_FILE_PREFIX, OUTPUT_FILE_SUFFIX);
        } catch (IOException e) {
            log.warn("mp3 임시파일을 만들지 못했습니다. cause={}", e.toString());
            throw new CustomException(AudioErrorCode.AUDIO_CONVERT_FAILED);
        }
    }

    private Path createLogFile() {
        try {
            return Files.createTempFile(LOG_FILE_PREFIX, LOG_FILE_SUFFIX);
        } catch (IOException e) {
            log.warn("ffmpeg 로그 임시파일을 만들지 못했습니다. cause={}", e.toString());
            throw new CustomException(AudioErrorCode.AUDIO_CONVERT_FAILED);
        }
    }

    private void deleteQuietly(Path file) {
        try {
            Files.deleteIfExists(file);
        } catch (IOException e) {
            log.warn("임시파일을 지우지 못했습니다. path={}", file, e);
        }
    }
}
