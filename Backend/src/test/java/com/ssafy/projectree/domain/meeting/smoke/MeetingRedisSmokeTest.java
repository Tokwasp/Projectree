package com.ssafy.projectree.domain.meeting.smoke;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisEntry;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisReader;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationOutcome;
import com.ssafy.projectree.domain.meeting.service.MeetingSynchronizationService;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeFalse;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@Tag("smoke")
@ActiveProfiles({"test", "smoke"})
@SpringBootTest
@EnabledIfEnvironmentVariable(named = "MEETING_REDIS_SMOKE_ENABLED", matches = "(?i)true")
@EnabledIfEnvironmentVariable(named = "MEETING_REDIS_SMOKE_ALLOW_WRITE", matches = "(?i)true")
class MeetingRedisSmokeTest {

    private static final String KEY_PREFIX = "meeting:project:";
    private static final Duration KEY_TTL = Duration.ofSeconds(60);

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private StringRedisTemplate redisTemplate;

    @Autowired
    private MeetingRoomRedisReader redisReader;

    @Autowired
    private MeetingSynchronizationService synchronizationService;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private Environment environment;

    @AfterEach
    void cleanDatabase() {
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void synchronizesHashAndSkipsWrongTypeOnStagingRedis() {
        verifySafetyGuards();

        Project project = Project.builder()
                .title("meeting-redis-smoke")
                .content("temporary smoke fixture")
                .build();
        ProjectMember creator = ProjectMember.createMember(722, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        String validRoomName = UUID.randomUUID().toString();
        String wrongTypeKey = KEY_PREFIX + (project.getId() + 1);
        String validKey = KEY_PREFIX + project.getId();

        redisTemplate.opsForHash().putAll(
                validKey,
                Map.of(
                        "creator", Integer.toString(creator.getMemberId()),
                        "room", validRoomName
                )
        );
        redisTemplate.expire(validKey, KEY_TTL);
        redisTemplate.opsForValue().set(wrongTypeKey, "invalid-smoke-value", KEY_TTL);

        assertThat(redisTemplate.getExpire(validKey, TimeUnit.SECONDS)).isPositive();
        assertThat(redisTemplate.getExpire(wrongTypeKey, TimeUnit.SECONDS)).isPositive();

        var entries = redisReader.findAll();
        assertThat(entries)
                .extracting(MeetingRoomRedisEntry::roomName)
                .contains(validRoomName);

        MeetingRoomRedisEntry validEntry = entries.stream()
                .filter(entry -> validRoomName.equals(entry.roomName()))
                .findFirst()
                .orElseThrow();
        assertThat(synchronizationService.synchronize(validEntry))
                .isEqualTo(MeetingSynchronizationOutcome.CREATED);
        assertThat(synchronizationService.synchronize(validEntry))
                .isEqualTo(MeetingSynchronizationOutcome.ALREADY_EXISTS);

        assertThat(meetingRepository.findByRoomName(validRoomName))
                .get()
                .extracting(Meeting::getCreatorMemberId)
                .isEqualTo(creator.getMemberId());
        assertThat(meetingRepository.count()).isEqualTo(1);
        assertThat(redisTemplate.hasKey(validKey)).isTrue();
        assertThat(redisTemplate.hasKey(wrongTypeKey)).isTrue();
    }

    private void verifySafetyGuards() {
        assumeTrue(Boolean.parseBoolean(System.getenv("MEETING_REDIS_SMOKE_ENABLED")));
        assumeTrue(Boolean.parseBoolean(System.getenv("MEETING_REDIS_SMOKE_ALLOW_WRITE")));
        assumeFalse(
                Arrays.stream(environment.getActiveProfiles())
                        .anyMatch(profile -> profile.equalsIgnoreCase("prod")
                                || profile.equalsIgnoreCase("production")),
                "Smoke Test is forbidden with a production profile"
        );

        String redisHost = environment.getRequiredProperty("spring.data.redis.host");
        String normalizedHost = redisHost.toLowerCase(java.util.Locale.ROOT);
        assumeFalse(
                normalizedHost.contains("prod")
                        || normalizedHost.contains("production")
                        || normalizedHost.equals("localhost")
                        || normalizedHost.equals("127.0.0.1"),
                "Smoke Test requires a non-production staging/dev Redis host"
        );
    }
}
