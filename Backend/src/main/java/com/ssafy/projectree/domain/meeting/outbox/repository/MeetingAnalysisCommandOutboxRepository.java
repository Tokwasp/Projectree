package com.ssafy.projectree.domain.meeting.outbox.repository;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.Modifying;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface MeetingAnalysisCommandOutboxRepository
        extends JpaRepository<MeetingAnalysisCommandOutbox, Integer> {

    Optional<MeetingAnalysisCommandOutbox> findByCommandId(String commandId);

    Optional<MeetingAnalysisCommandOutbox> findByMeetingIdAndCommandType(
            int meetingId,
            MeetingAnalysisCommandType commandType
    );

    long countByMeetingId(int meetingId);

    @Query("""
            select (count(outbox) > 0)
            from MeetingAnalysisCommandOutbox outbox
            where outbox.commandType = :commandType
              and outbox.targetProjectId = :projectId
              and outbox.status <> :failedStatus
              and not exists (
                    select inbox.id
                    from MeetingAnalysisResultInbox inbox
                    where inbox.commandId = outbox.commandId
                      and inbox.eventType = :terminalEventType
              )
            """)
    boolean existsInFlightGraphMutationByProjectId(
            @Param("projectId") int projectId,
            @Param("commandType") MeetingAnalysisCommandType commandType,
            @Param("failedStatus") MeetingAnalysisOutboxStatus failedStatus,
            @Param("terminalEventType") AnalysisResultEventType terminalEventType
    );

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            delete from MeetingAnalysisCommandOutbox outbox
            where outbox.targetProjectId = :projectId
               or outbox.meeting.project.id = :projectId
            """)
    void deleteAllByProjectId(@Param("projectId") int projectId);

    @Query("""
            select o
            from MeetingAnalysisCommandOutbox o
            join fetch o.meeting m
            join fetch m.project
            where o.commandId = :commandId
            """)
    Optional<MeetingAnalysisCommandOutbox> findByCommandIdWithMeetingAndProject(
            @Param("commandId") String commandId
    );

    @Query(value = """
            SELECT *
            FROM meeting_analysis_command_outbox
            WHERE (
                    status = 'PENDING'
                    AND next_attempt_at <= :now
                    AND attempt_count < :maxAttempts
                  )
               OR (
                    status = 'PUBLISHING'
                    AND lease_until <= :now
                  )
            ORDER BY created_at ASC, id ASC
            LIMIT :batchSize
            FOR UPDATE SKIP LOCKED
            """, nativeQuery = true)
    List<MeetingAnalysisCommandOutbox> findClaimableForUpdate(
            @Param("now") LocalDateTime now,
            @Param("maxAttempts") int maxAttempts,
            @Param("batchSize") int batchSize
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select o
            from MeetingAnalysisCommandOutbox o
            where o.id = :outboxId
              and o.status = com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus.PUBLISHING
              and o.claimToken = :claimToken
            """)
    Optional<MeetingAnalysisCommandOutbox> findOwnedPublishingForUpdate(
            @Param("outboxId") int outboxId,
            @Param("claimToken") String claimToken
    );
}
