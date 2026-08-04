package com.ssafy.projectree.domain.notification.repository;

import com.ssafy.projectree.domain.notification.entity.Notification;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NotificationRepository extends JpaRepository<Notification, Integer> {

    /**
     * 조건을 메서드 이름으로 다 표현하면 findByReceiverIdAndIdGreaterThanOrderByIdAsc 가 되어
     * 무엇을 찾는 쿼리인지가 오히려 안 읽힌다. 이름은 의도로 짓고 조건은 여기 드러낸다.
     */
    @Query("""
            select n from Notification n
            where n.receiverId = :memberId
              and n.id > :lastEventId
            order by n.id asc
            """)
    List<Notification> findNotReceivedMessages(@Param("memberId") int memberId,
                                               @Param("lastEventId") int lastEventId);
}
