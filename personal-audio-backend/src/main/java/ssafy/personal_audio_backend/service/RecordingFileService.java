package ssafy.personal_audio_backend.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import ssafy.personal_audio_backend.global.exception.CustomException;
import ssafy.personal_audio_backend.service.exception.AudioErrorCode;

@Slf4j
@Service
public class RecordingFileService {

    private static final String TEMP_FILE_PREFIX = "recording-";

    private final S3Client s3Client;
    private final String bucket;

    public RecordingFileService(S3Client s3Client, @Value("${app.s3.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    public Path downloadToTempFile(String objectKey) {
        Path tempFile = createTempFile(objectKey);

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .build();

        try (ResponseInputStream<GetObjectResponse> objectStream = s3Client.getObject(request)) {
            Files.copy(objectStream, tempFile, StandardCopyOption.REPLACE_EXISTING);
            log.info("audio downloaded. bucket={}, objectKey={}, path={}, size={}",
                    bucket, objectKey, tempFile, Files.size(tempFile));

            return tempFile;
        } catch (NoSuchKeyException e) {
            delete(tempFile);
            log.warn("audio not found. bucket={}, objectKey={}", bucket, objectKey);
            throw new CustomException(AudioErrorCode.AUDIO_NOT_FOUND);
        } catch (SdkException | IOException e) {
            delete(tempFile);
            log.warn("audio download failed. bucket={}, objectKey={}, cause={}", bucket, objectKey, e.toString());
            throw new CustomException(AudioErrorCode.AUDIO_DOWNLOAD_FAILED);
        }
    }

    public void delete(Path file) {
        try {
            Files.deleteIfExists(file);
        } catch (IOException e) {
            log.warn("failed to delete temp file. path={}", file, e);
        }
    }

    private Path createTempFile(String objectKey) {
        try {
            return Files.createTempFile(TEMP_FILE_PREFIX, extensionOf(objectKey));
        } catch (IOException e) {
            throw new CustomException(AudioErrorCode.AUDIO_DOWNLOAD_FAILED);
        }
    }

    private static String extensionOf(String objectKey) {
        int lastDot = objectKey.lastIndexOf('.');
        if (lastDot < 0) {
            return "";
        }
        return objectKey.substring(lastDot);
    }
}
