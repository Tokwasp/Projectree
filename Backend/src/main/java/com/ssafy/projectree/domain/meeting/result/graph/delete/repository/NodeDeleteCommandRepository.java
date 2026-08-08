package com.ssafy.projectree.domain.meeting.result.graph.delete.repository;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface NodeDeleteCommandRepository extends JpaRepository<NodeDeleteCommand, Long> {

    Optional<NodeDeleteCommand> findByCommandId(String commandId);

    Optional<NodeDeleteCommand> findByProjectIdAndCommandId(int projectId, String commandId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select command
            from NodeDeleteCommand command
            where command.projectId = :projectId
              and command.commandId = :commandId
            """)
    Optional<NodeDeleteCommand> findByProjectIdAndCommandIdForUpdate(
            @Param("projectId") int projectId,
            @Param("commandId") String commandId
    );

    boolean existsByProjectIdAndStatus(int projectId, NodeDeleteCommandStatus status);
}
