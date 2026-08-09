package com.ssafy.projectree.global.s3;

import com.ssafy.projectree.global.config.s3.S3Properties;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.s3.dto.response.PresignedUrlResponse;
import com.ssafy.projectree.global.s3.exception.S3ErrorCode;
import io.awspring.cloud.s3.S3Template;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.net.URI;
import java.net.URL;
import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

@ExtendWith(MockitoExtension.class)
class S3ServiceTest {

    private static final String BUCKET = "projectree-bucket";
    private static final long EXPIRE_SECONDS = 300L;

    private S3Service s3Service;

    @Mock
    private S3Template s3Template;

    @BeforeEach
    void setUp() {
        // S3Properties 는 생성자 바인딩 전용이라 @InjectMocks 대신 직접 조립한다.
        s3Service = new S3Service(s3Template, new S3Properties(BUCKET, EXPIRE_SECONDS));
    }

    @DisplayName("키는 '업로드타입/날짜/UUID' 두 단계 폴더로만 만들고 원본 파일명을 쓰지 않는다.")
    @Test
    void generatePresignedUrl() {
        // given
        givenSignedUrl("https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/key?X-Amz-Signature=abc");
        ArgumentCaptor<String> fileKeyCaptor = ArgumentCaptor.forClass(String.class);

        // when
        s3Service.generatePresignedUrl(UploadType.PROFILE);

        // then
        then(s3Template).should().createSignedPutURL(
                eq(BUCKET),
                fileKeyCaptor.capture(),
                eq(Duration.ofSeconds(EXPIRE_SECONDS)),
                any(),
                any()
        );
        // 날짜를 yyyy/MM/dd 로 되돌리면 폴더가 3단계로 늘어나 여기서 걸린다.
        assertThat(fileKeyCaptor.getValue())
                .matches("profile/\\d{4}_\\d{2}_\\d{2}/[0-9a-f-]{36}");
    }

    @DisplayName("발급할 때마다 서로 다른 키를 만들어 기존 파일을 덮어쓰지 않는다.")
    @Test
    void generatePresignedUrl_generatesUniqueKey() {
        // given
        givenSignedUrl("https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/key?X-Amz-Signature=abc");
        ArgumentCaptor<String> fileKeyCaptor = ArgumentCaptor.forClass(String.class);

        // when
        s3Service.generatePresignedUrl(UploadType.PROJECT);
        s3Service.generatePresignedUrl(UploadType.PROJECT);

        // then
        then(s3Template).should(times(2)).createSignedPutURL(
                anyString(), fileKeyCaptor.capture(), any(Duration.class), any(), any());
        assertThat(fileKeyCaptor.getAllValues()).doesNotHaveDuplicates();
    }

    @DisplayName("Content-Type 을 서명에 넣지 않아 클라이언트가 어떤 형식이든 올릴 수 있다.")
    @Test
    void generatePresignedUrl_doesNotSignContentType() {
        // given
        givenSignedUrl("https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/key?X-Amz-Signature=abc");

        // when
        s3Service.generatePresignedUrl(UploadType.PROFILE);

        // then
        then(s3Template).should().createSignedPutURL(
                anyString(), anyString(), any(Duration.class), eq(null), eq(null));
    }

    @DisplayName("조회용 URL은 presigned URL에서 서명 쿼리스트링을 제거한 값이다.")
    @Test
    void generatePresignedUrl_imageUrlHasNoQuery() {
        // given
        String objectUrl = "https://projectree-bucket.s3.ap-northeast-2.amazonaws.com/profile/2026_08_03/uuid";
        givenSignedUrl(objectUrl + "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc");

        // when
        PresignedUrlResponse response = s3Service.generatePresignedUrl(UploadType.PROFILE);

        // then
        assertThat(response.getImageUrl()).isEqualTo(objectUrl);
    }

    @DisplayName("서명 발급이 실패하면 원인 예외를 감춘 PRESIGNED_URL_FAILED 예외로 바꿔 던진다.")
    @Test
    void generatePresignedUrl_whenSigningFails() {
        // given
        given(s3Template.createSignedPutURL(anyString(), anyString(), any(Duration.class), any(), any()))
                .willThrow(new IllegalStateException("credentials not found"));

        // when // then
        assertThatThrownBy(() -> s3Service.generatePresignedUrl(UploadType.PROFILE))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(S3ErrorCode.PRESIGNED_URL_FAILED);
    }

    private void givenSignedUrl(String url) {
        given(s3Template.createSignedPutURL(anyString(), anyString(), any(Duration.class), any(), any()))
                .willReturn(toUrl(url));
    }

    private URL toUrl(String url) {
        try {
            return URI.create(url).toURL();
        } catch (Exception e) {
            throw new IllegalArgumentException(e);
        }
    }
}
