package com.ssafy.projectree.global.config.notification;

import com.ssafy.projectree.domain.notification.service.NotificationSubscriber;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationConfig {

    public static final String NOTIFICATION_TOPIC = "NOTIFICATION";

    /**
     * RedisConnectionFactory 는 Spring Session 이 이미 만들어 둔 것을 그대로 쓴다.
     * 이중화된 모든 인스턴스가 같은 토픽을 구독하고, 연결을 들고 있는 인스턴스만 반응한다.
     */
    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            NotificationSubscriber notificationSubscriber
    ) {
        RedisMessageListenerContainer container = new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(notificationSubscriber, new ChannelTopic(NOTIFICATION_TOPIC));

        return container;
    }
}
