package com.ssafy.projectree.global.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 초대 메일 스위퍼와 알림 하트비트가 모두 이 스위치 하나에 달려 있다.
 * 예전에는 초대 메일 전용 플래그가 전역 @EnableScheduling 을 좌우해서,
 * 그 값을 끄면 관계없는 하트비트까지 조용히 죽었다.
 * <p>
 * 설정이 없으면 켜진 것으로 본다. 끄는 쪽(테스트)만 명시하면 된다.
 */
@Configuration
@EnableScheduling
@ConditionalOnProperty(
        name = "app.scheduling.enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class SchedulingConfig {
}
