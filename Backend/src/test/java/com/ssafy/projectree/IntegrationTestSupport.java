package com.ssafy.projectree;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

@ActiveProfiles("test")
@Transactional
@SpringBootTest
public abstract class IntegrationTestSupport {

    @MockitoBean
    protected GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    protected NaverOAuthClient naverOAuthClient;

    @MockitoBean
    protected RedisMessageListenerContainer redisMessageListenerContainer;

}
