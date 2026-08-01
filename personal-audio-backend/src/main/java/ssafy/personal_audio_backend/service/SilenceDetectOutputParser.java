package ssafy.personal_audio_backend.service;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import ssafy.personal_audio_backend.domain.speech.SpeechSegment;
import ssafy.personal_audio_backend.domain.speech.SpeechSegments;
import ssafy.personal_audio_backend.global.exception.CustomException;
import ssafy.personal_audio_backend.service.exception.AudioErrorCode;

@Slf4j
@Component
public class SilenceDetectOutputParser {

    private static final Pattern DURATION =
            Pattern.compile("Duration:\\s*(\\d+):(\\d{2}):(\\d{2}(?:\\.\\d+)?)");
    private static final Pattern SILENCE_START =
            Pattern.compile("silence_start:\\s*(-?\\d+(?:\\.\\d+)?)");
    private static final Pattern SILENCE_END =
            Pattern.compile("silence_end:\\s*(-?\\d+(?:\\.\\d+)?)");

    private static final int SECONDS_PER_MINUTE = 60;
    private static final int SECONDS_PER_HOUR = 3_600;

    public SpeechSegments parse(String ffmpegOutput) {
        double totalSeconds = parseTotalSeconds(ffmpegOutput);
        List<double[]> silences = parseSilences(ffmpegOutput, totalSeconds);

        return toSpeechSegments(silences, totalSeconds);
    }

    private double parseTotalSeconds(String ffmpegOutput) {
        Matcher matcher = DURATION.matcher(ffmpegOutput);
        if (!matcher.find()) {
            log.warn("ffmpeg 출력에서 재생 길이를 찾지 못했습니다.");
            throw new CustomException(AudioErrorCode.SPEECH_ANALYSIS_FAILED);
        }

        return Integer.parseInt(matcher.group(1)) * SECONDS_PER_HOUR
                + Integer.parseInt(matcher.group(2)) * SECONDS_PER_MINUTE
                + Double.parseDouble(matcher.group(3));
    }

    private List<double[]> parseSilences(String ffmpegOutput, double totalSeconds) {
        List<Double> starts = findAll(SILENCE_START, ffmpegOutput);
        List<Double> ends = findAll(SILENCE_END, ffmpegOutput);

        List<double[]> silences = new ArrayList<>();
        for (int i = 0; i < starts.size(); i++) {
            double start = clamp(starts.get(i), totalSeconds);
            double end = i < ends.size() ? clamp(ends.get(i), totalSeconds) : totalSeconds;
            silences.add(new double[]{start, end});
        }
        return silences;
    }

    private double clamp(double seconds, double totalSeconds) {
        return Math.min(Math.max(0.0, seconds), totalSeconds);
    }

    private List<Double> findAll(Pattern pattern, String text) {
        List<Double> values = new ArrayList<>();
        Matcher matcher = pattern.matcher(text);
        while (matcher.find()) {
            values.add(Double.parseDouble(matcher.group(1)));
        }
        return values;
    }

    private SpeechSegments toSpeechSegments(List<double[]> silences, double totalSeconds) {
        List<SpeechSegment> speeches = new ArrayList<>();
        double cursor = 0.0;

        for (double[] silence : silences) {
            addIfNotEmpty(speeches, cursor, silence[0]);
            cursor = Math.max(cursor, silence[1]);
        }
        addIfNotEmpty(speeches, cursor, totalSeconds);

        return SpeechSegments.of(speeches);
    }

    private void addIfNotEmpty(List<SpeechSegment> speeches, double start, double end) {
        if (end > start) {
            speeches.add(SpeechSegment.of(start, end));
        }
    }
}
