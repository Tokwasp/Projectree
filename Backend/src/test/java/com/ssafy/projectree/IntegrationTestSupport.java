package com.ssafy.projectree;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

@ActiveProfiles("test")
@Transactional
@SpringBootTest
public abstract class IntegrationTestSupport {

    // 외부 시스템(Google OAuth) 호출은 통합 테스트에서 절대 실제로 발생시키지 않는다.
    @MockitoBean
    protected GoogleOAuthClient googleOAuthClient;

}
