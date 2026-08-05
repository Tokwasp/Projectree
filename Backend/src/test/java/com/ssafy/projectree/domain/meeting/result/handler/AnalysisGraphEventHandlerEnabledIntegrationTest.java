package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.dispatcher.AnalysisResultEventDispatcher;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.meeting-analysis.graph-snapshot.s3.enabled=true",
        "app.meeting-analysis.graph-snapshot.s3.expected-bucket=graph-bucket",
        "app.meeting-analysis.graph-snapshot.s3.region=ap-northeast-2"
})
class AnalysisGraphEventHandlerEnabledIntegrationTest extends IntegrationTestSupport {

    @Autowired private AnalysisGraphEventHandler handler;
    @Autowired private AnalysisResultEventDispatcher dispatcher;

    @Test
    void registersGraphHandlerWhenGraphSnapshotS3IsEnabled() {
        assertThat(AopUtils.isAopProxy(handler)).isTrue();
        assertThat(dispatcher.supports(AnalysisResultEventType.PROJECT_GRAPH_CHANGED)).isTrue();
    }
}
