package com.ssafy.projectree.global.s3;

import com.ssafy.projectree.global.config.s3.S3Properties;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.s3.dto.response.PresignedUrlResponse;
import com.ssafy.projectree.global.s3.exception.S3ErrorCode;
import io.awspring.cloud.s3.S3Template;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.net.URL;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class S3Service {

    private static final DateTimeFormatter KEY_DATE_FORMAT = DateTimeFormatter.ofPattern("yyyy_MM_dd");

    private final S3Template s3Template;
    private final S3Properties s3Properties;

    public PresignedUrlResponse generatePresignedUrl(UploadType type) {
        String fileKey = generateFileKey(type);
        URL presignedUrl = createSignedPutUrl(fileKey);

        return PresignedUrlResponse.of(presignedUrl.toString(), toImageUrl(presignedUrl));
    }

    private URL createSignedPutUrl(String fileKey) {
        try {
            return s3Template.createSignedPutURL(
                    s3Properties.getBucket(),
                    fileKey,
                    Duration.ofSeconds(s3Properties.getPresignedUrlExpireSeconds()),
                    null,
                    null
            );
        } catch (RuntimeException e) {
            log.error("presigned url 발급 실패: key={}", fileKey, e);
            throw new CustomException(S3ErrorCode.PRESIGNED_URL_FAILED);
        }
    }

    private String generateFileKey(UploadType type) {
        return "%s/%s/%s".formatted(
                type.getDirectory(),
                LocalDate.now().format(KEY_DATE_FORMAT),
                UUID.randomUUID()
        );
    }

    private String toImageUrl(URL presignedUrl) {
        String url = presignedUrl.toString();
        int queryIndex = url.indexOf('?');

        return queryIndex == -1 ? url : url.substring(0, queryIndex);
    }
}
