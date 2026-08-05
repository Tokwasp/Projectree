package com.ssafy.projectree.domain.meeting.infrastructure.redis;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MeetingSyncProperties.class)
public class MeetingSyncRedisConfig {
}
