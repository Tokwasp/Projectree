package ssafy.personal_audio_backend.domain.review.feedback;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class FillerWords {

    private static final Set<String> CLEAR = Set.of(
            "어", "어어", "음", "음음", "으음", "아", "아아", "에", "에에", "흠", "응",
            "그", "그으", "저", "저어", "뭐",
            "뭐랄까", "뭐지", "뭐냐", "뭐냐면",
            "저기", "있잖아", "있잖아요", "거시기"
    );

    private static final Set<String> AMBIGUOUS = Set.of(
            "근데", "그런데", "그니까", "그러니까", "그래가지고", "그래갖고",
            "그냥", "이제", "인제", "막", "약간", "좀", "뭔가",
            "아무튼", "암튼", "어쨌든", "하여튼", "여하튼",
            "아니", "이렇게", "그렇게", "그쵸", "그죠",
            "진짜", "되게", "완전",
            // 지시어를 말 사이에 끼워 넣는 습관 ("그 이거… 저거…")
            "이거", "이걸", "저거", "저건", "그거", "그걸"
    );

    private static final Set<String> ALL = Stream.concat(CLEAR.stream(), AMBIGUOUS.stream())
            .collect(Collectors.toUnmodifiableSet());

    private static final String TRANSCRIPTION_HINT =
            "어… 음… 그러니까 저기, 그 뭐랄까… 약간 이제 막 그냥, 근데 있잖아요 "
                    + "아 네 그래가지고 어쨌든 뭐 좀 뭔가 그런… 흠, 아니 그니까 그으…";

    private static final Pattern PUNCTUATION = Pattern.compile("[.,!?…\"'()\\[\\]]");
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");
    private static final String EMPTY = "";

    private FillerWords() {
    }

    public static String transcriptionHint() {
        return TRANSCRIPTION_HINT;
    }

    public static int size() {
        return ALL.size();
    }

    public static int clearSize() {
        return CLEAR.size();
    }

    public static Map<String, Long> tallyClear(String text) {
        return tally(text, CLEAR);
    }

    public static Map<String, Long> tallyAmbiguous(String text) {
        return tally(text, AMBIGUOUS);
    }

    private static Map<String, Long> tally(String text, Set<String> vocabulary) {
        return matchesIn(text, vocabulary).stream()
                .collect(Collectors.groupingBy(word -> word, Collectors.counting()))
                .entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed()
                        .thenComparing(Map.Entry.comparingByKey()))
                .collect(Collectors.toMap(
                        Map.Entry::getKey,
                        Map.Entry::getValue,
                        (left, right) -> left,
                        LinkedHashMap::new));
    }

    private static List<String> matchesIn(String text, Set<String> vocabulary) {
        if (text == null || text.isBlank()) {
            return List.of();
        }

        return WHITESPACE.splitAsStream(text)
                .map(token -> PUNCTUATION.matcher(token).replaceAll(EMPTY))
                .filter(vocabulary::contains)
                .toList();
    }
}
