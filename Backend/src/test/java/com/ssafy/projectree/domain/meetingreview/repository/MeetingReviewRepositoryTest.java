package com.ssafy.projectree.domain.meetingreview.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class MeetingReviewRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private MeetingReviewRepository meetingReviewRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("프로젝트와 회원 기준으로 가장 최근 회의 리뷰를 조회한다.")
    @Test
    void getRecentReview() {
        // given
        int projectId = 1;
        int memberId = 10;

        meetingReviewRepository.save(MeetingReview.of("room-old", projectId, memberId));
        MeetingReview latest = meetingReviewRepository.save(MeetingReview.of("room-latest", projectId, memberId));

        // 같은 프로젝트의 다른 회원, 같은 회원의 다른 프로젝트 — 섞이지 않아야 함
        meetingReviewRepository.save(MeetingReview.of("room-other-member", projectId, 20));
        meetingReviewRepository.save(MeetingReview.of("room-other-project", 2, memberId));
        flushAndClear();

        // when
        Optional<MeetingReview> result = meetingReviewRepository.getRecentReview(projectId, memberId);

        // then
        assertThat(result).isPresent();
        assertThat(result.get().getRoomName()).isEqualTo(latest.getRoomName());
    }

    @DisplayName("프로젝트와 회원 기준으로 가장 최근 회의 리뷰를 조회할 때, 리뷰가 하나도 없으면 빈 값을 반환한다.")
    @Test
    void getRecentReviewWhenNoReviewExists() {
        // when
        Optional<MeetingReview> result = meetingReviewRepository.getRecentReview(1, 10);

        // then
        assertThat(result).isEmpty();
    }

    @DisplayName("roomName으로 해당 회의에 참석한 회원들의 리뷰를 모두 조회한다.")
    @Test
    void findAllByRoomName() {
        // given
        String roomName = "room-a";
        meetingReviewRepository.save(MeetingReview.of(roomName, 1, 10));
        meetingReviewRepository.save(MeetingReview.of(roomName, 1, 20));
        meetingReviewRepository.save(MeetingReview.of("room-b", 1, 30));
        flushAndClear();

        // when
        List<MeetingReview> result = meetingReviewRepository.findAllByRoomName(roomName);

        // then
        assertThat(result).hasSize(2)
                .extracting("roomName", "memberId")
                .containsExactlyInAnyOrder(
                        tuple(roomName, 10),
                        tuple(roomName, 20)
                );
    }

    @DisplayName("roomName으로 조회할 때, 해당하는 회의가 없으면 빈 목록을 반환한다.")
    @Test
    void findAllByRoomNameWhenRoomNotExists() {
        // when
        List<MeetingReview> result = meetingReviewRepository.findAllByRoomName("no-such-room");

        // then
        assertThat(result).isEmpty();
    }

    private void flushAndClear() {
        entityManager.flush();
        entityManager.clear();
    }
}
