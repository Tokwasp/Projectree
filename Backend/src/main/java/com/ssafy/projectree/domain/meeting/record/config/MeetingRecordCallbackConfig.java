package com.ssafy.projectree.domain.meeting.record.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MeetingRecordCallbackProperties.class)
public class MeetingRecordCallbackConfig {
}
