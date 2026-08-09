package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface ProjectGraphSyncRepository extends JpaRepository<ProjectGraphSync, Integer> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select sync from ProjectGraphSync sync where sync.projectId = :projectId")
    Optional<ProjectGraphSync> findByProjectIdForUpdate(@Param("projectId") int projectId);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from ProjectGraphSync sync where sync.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
