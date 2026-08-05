package com.ssafy.projectree.domain.notification.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Notification extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @Column(name = "receiver_id", nullable = false)
    private int receiverId;

    @Enumerated(EnumType.STRING)
    private NotificationType type;

    @Builder
    private Notification(NotificationType type, int receiverId) {
        this.type = type;
        this.receiverId = receiverId;
    }

    public static Notification of(NotificationType type, int receiverId) {
        return Notification.builder()
                .receiverId(receiverId)
                .type(type)
                .build();
    }

    public String getMessage() {
        return type.getMessage();
    }
}
