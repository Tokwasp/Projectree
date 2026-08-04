package com.ssafy.projectree.domain.notification.repository;

import org.springframework.stereotype.Repository;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * SseEmitter 는 직렬화할 수 없는 살아 있는 HTTP 연결이라 DB나 Redis에 넣어 공유할 수 없다.
 * 그래서 JPA Repository 가 아니라 이 인스턴스의 메모리에만 존재하는 저장소다.
 * <p>
 * ConcurrentHashMap 이어야 한다. 요청 스레드(구독), Redis 리스너 스레드(전송),
 * 타임아웃 콜백 스레드가 동시에 이 맵을 건드린다.
 */
@Repository
public class EmitterRepository {

    private final Map<String, SseEmitter> emitters = new ConcurrentHashMap<>();

    public SseEmitter save(String emitterId, SseEmitter emitter) {
        emitters.put(emitterId, emitter);

        return emitter;
    }

    public void deleteById(String emitterId) {
        emitters.remove(emitterId);
    }

    /**
     * 구분자를 붙여야 memberId=1 이 11_..., 123_... 에 걸려 남의 알림이 가는 일을 막는다.
     */
    public Map<String, SseEmitter> findAllByMemberId(int memberId) {
        String prefix = memberId + "_";

        return emitters.entrySet().stream()
                .filter(entry -> entry.getKey().startsWith(prefix))
                .collect(Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue));
    }

    /**
     * 하트비트가 순회하는 도중 전송 실패로 deleteById 가 원본을 건드려도 안전하도록 복사본을 준다.
     */
    public Map<String, SseEmitter> findAll() {
        return Map.copyOf(emitters);
    }
}
