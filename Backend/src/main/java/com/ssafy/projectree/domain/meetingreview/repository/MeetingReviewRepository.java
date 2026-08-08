package com.ssafy.projectree.domain.meetingreview.repository;

import com.ssafy.projectree.domain.meetingreview.MeetingReview;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface MeetingReviewRepository extends JpaRepository<MeetingReview, Integer> {

    @Query("""
            select mr 
            from MeetingReview mr
            where mr.memberId = :memberId and mr.projectId = :projectId
            order by mr.id desc
            limit 1
            """)
    Optional<MeetingReview> getRecentReview(@Param("projectId") int projectId, @Param("memberId") int memberId);

    @Query("""
        select mr
        from MeetingReview mr
        where mr.roomName = :roomName
        """
    )
    List<MeetingReview> findAllByRoomName(@Param("roomName") String roomName);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from MeetingReview review where review.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
