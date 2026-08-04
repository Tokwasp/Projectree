package com.ssafy.projectree.domain.notification.repository;

import com.ssafy.projectree.domain.notification.entity.Notification;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NotificationRepository extends JpaRepository<Notification, Integer> {

    @Query("""
            select n from Notification n
            where n.receiverId = :memberId
              and n.id > :lastEventId
            order by n.id asc
            """)
    List<Notification> findNotReceivedMessages(@Param("memberId") int memberId,
                                               @Param("lastEventId") int lastEventId);
}
