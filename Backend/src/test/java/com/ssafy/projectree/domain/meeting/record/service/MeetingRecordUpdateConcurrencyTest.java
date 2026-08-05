package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordUpdateRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordUpdateResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.reset;

@ActiveProfiles("test")
@SpringBootTest
class MeetingRecordUpdateConcurrencyTest {

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private MeetingRecordUpdateService service;

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private MeetingRecordContentCodec contentCodec;

    @MockitoSpyBean
    private MeetingRecordContentEncoder contentEncoder;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @PersistenceContext
    private EntityManager entityManager;

    @AfterEach
    void cleanUp() {
        reset(contentEncoder);
        meetingRecordRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("같은 version의 실제 동시 수정은 하나만 성공하고 JPA @Version이 다른 요청을 막는다.")
    @Test
    void allowsExactlyOneConcurrentUpdate() throws Exception {
        Fixture fixture = fixture();
        MeetingRecordUpdateRequest firstRequest = request("A");
        MeetingRecordUpdateRequest secondRequest = request("B");
        CountDownLatch bothPassedVersionCheck = new CountDownLatch(2);
        CountDownLatch startEncoding = new CountDownLatch(1);

        doAnswer(invocation -> {
            bothPassedVersionCheck.countDown();
            startEncoding.await();
            return invocation.callRealMethod();
        }).when(contentEncoder).encode(anyList(), anyList(), anyList(), anyList());

        List<Object> results;
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<Object> first = executor.submit(
                    () -> update(fixture, firstRequest)
            );
            Future<Object> second = executor.submit(
                    () -> update(fixture, secondRequest)
            );
            bothPassedVersionCheck.await();
            startEncoding.countDown();
            results = List.of(first.get(), second.get());
        } finally {
            reset(contentEncoder);
        }

        assertThat(results.stream().filter(MeetingRecordUpdateResponse.class::isInstance))
                .hasSize(1);
        assertThat(results.stream().filter(OptimisticLockingFailureException.class::isInstance))
                .hasSize(1);

        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(stored.getVersion()).isEqualTo(1L);
        assertThat(stored.getTitle()).isIn(firstRequest.title(), secondRequest.title());

        MeetingRecordUpdateRequest winner = stored.getTitle().equals(firstRequest.title())
                ? firstRequest
                : secondRequest;
        assertThat(contentCodec.decode(stored.getSummaryJson()))
                .containsExactlyElementsOf(winner.summary());
        assertThat(contentCodec.decode(stored.getDecisionsJson()))
                .containsExactlyElementsOf(winner.decisions());
        assertThat(contentCodec.decode(stored.getNextTodosJson()))
                .containsExactlyElementsOf(winner.nextTodos());
        assertThat(contentCodec.decode(stored.getIssuesJson()))
                .containsExactlyElementsOf(winner.issues());
    }

    private Object update(Fixture fixture, MeetingRecordUpdateRequest request) {
        try {
            return service.update(
                    fixture.projectId(),
                    fixture.meetingId(),
                    fixture.memberId(),
                    request
            );
        } catch (RuntimeException exception) {
            return exception;
        }
    }

    private Fixture fixture() {
        return new TransactionTemplate(transactionManager).execute(status -> {
            String suffix = UUID.randomUUID().toString();
            Member member = memberRepository.save(
                    Member.builder()
                            .email("member-" + suffix + "@example.com")
                            .name("member")
                            .build()
            );
            Project project = Project.builder().title("project").content("content").build();
            ProjectMember creator = ProjectMember.createMember(
                    member.getId(),
                    ProjectRole.OWNER
            );
            project.addMember(creator);
            projectRepository.save(project);

            Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
            meetingRepository.save(meeting);
            meetingRecordRepository.save(MeetingRecord.create(
                    meeting,
                    UUID.randomUUID(),
                    "원본 제목",
                    contentCodec.encode(List.of("원본 요약")),
                    contentCodec.encode(List.of("원본 결정")),
                    contentCodec.encode(List.of("원본 할 일")),
                    contentCodec.encode(List.of("원본 이슈"))
            ));
            entityManager.flush();
            return new Fixture(project.getId(), meeting.getId(), member.getId());
        });
    }

    private MeetingRecordUpdateRequest request(String marker) {
        return new MeetingRecordUpdateRequest(
                marker + " 제목",
                List.of(marker + " 요약"),
                List.of(marker + " 결정"),
                List.of(marker + " 할 일"),
                List.of(marker + " 이슈"),
                0L
        );
    }

    private record Fixture(int projectId, int meetingId, int memberId) {
    }
}
