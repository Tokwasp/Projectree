package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.List;
import java.util.Optional;

public interface ProjectInvitationRepository extends JpaRepository<ProjectInvitation, Integer> {

    Optional<ProjectInvitation> findByProjectIdAndInviteeMemberId(int projectId, int inviteeMemberId);

    Optional<ProjectInvitation> findByTokenHash(String tokenHash);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<ProjectInvitation> findWithLockByTokenHash(String tokenHash);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<ProjectInvitation> findWithLockById(int id);

    List<ProjectInvitation> findAllByProjectIdAndStatus(int projectId, InvitationStatus status);
}
