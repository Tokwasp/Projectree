package com.ssafy.projectree.domain.notification.repository;

import org.springframework.stereotype.Repository;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

@Repository
public class EmitterRepository {

    private final Map<Integer, List<SseEmitter>> emitters = new ConcurrentHashMap<>();

    public SseEmitter save(int memberId, SseEmitter emitter) {
        emitters.compute(memberId, (id, emitterList) -> {
            List<SseEmitter> found = (emitterList == null) ? new CopyOnWriteArrayList<>() : emitterList;
            found.add(emitter);
            return found;
        });

        return emitter;
    }

    public void delete(int memberId, SseEmitter emitter) {
        emitters.compute(memberId, (id, emitterList) -> {
            if (emitterList == null) {
                return null;
            }
            emitterList.remove(emitter);
            return emitterList.isEmpty() ? null : emitterList;
        });
    }

    public List<SseEmitter> findAllByMemberId(int memberId) {
        return List.copyOf(emitters.getOrDefault(memberId, List.of()));
    }

    public Map<Integer, List<SseEmitter>> findAll() {
        return Map.copyOf(emitters);
    }
}
