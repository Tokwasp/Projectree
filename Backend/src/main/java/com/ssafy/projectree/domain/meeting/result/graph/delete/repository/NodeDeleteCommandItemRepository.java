package com.ssafy.projectree.domain.meeting.result.graph.delete.repository;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteItemType;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NodeDeleteCommandItemRepository
        extends JpaRepository<NodeDeleteCommandItem, Long> {

    @Query("""
            select item
            from NodeDeleteCommandItem item
            where item.command.commandId = :commandId
            order by item.id
            """)
    List<NodeDeleteCommandItem> findAllByCommandId(@Param("commandId") String commandId);

    @Query("""
            select distinct item.nodeId
            from NodeDeleteCommandItem item
            where item.command.projectId = :projectId
              and item.command.status =
                  com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus.PENDING
            """)
    List<String> findPendingNodeIdsByProjectId(@Param("projectId") int projectId);

    @Query("""
            select case when count(item) > 0 then true else false end
            from NodeDeleteCommandItem item
            where item.command.projectId = :projectId
              and item.command.status =
                  com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus.PENDING
              and item.nodeId = :nodeId
            """)
    boolean existsPendingNodeByProjectIdAndNodeId(
            @Param("projectId") int projectId,
            @Param("nodeId") String nodeId
    );

    @Query("""
            select item.nodeId
            from NodeDeleteCommandItem item
            where item.command.commandId = :commandId
              and item.itemType =
                  com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteItemType.REQUESTED
            order by item.id
            """)
    List<String> findRequestedNodeIdsByCommandId(@Param("commandId") String commandId);

    List<NodeDeleteCommandItem> findAllByCommandCommandIdAndItemTypeOrderById(
            String commandId,
            NodeDeleteItemType itemType
    );
}
