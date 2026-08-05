package com.ssafy.projectree.domain.meeting.result.graph.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3ClientBuilder;

import java.net.URI;

@Configuration
@EnableConfigurationProperties(GraphSnapshotProperties.class)
public class GraphSnapshotConfig {

    @Bean(name = "graphSnapshotS3Client", destroyMethod = "close")
    @ConditionalOnProperty(
            prefix = "app.meeting-analysis.graph-snapshot.s3",
            name = "enabled",
            havingValue = "true"
    )
    S3Client graphSnapshotS3Client(GraphSnapshotProperties properties) {
        GraphSnapshotProperties.S3 s3 = properties.s3();
        S3ClientBuilder builder = S3Client.builder()
                .region(Region.of(s3.region()))
                .credentialsProvider(DefaultCredentialsProvider.builder().build());
        if (!s3.endpointOverride().isBlank()) {
            builder.endpointOverride(URI.create(s3.endpointOverride()));
        }
        return builder.build();
    }
}
