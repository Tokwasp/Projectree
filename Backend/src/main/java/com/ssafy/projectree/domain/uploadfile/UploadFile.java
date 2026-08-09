package com.ssafy.projectree.domain.uploadfile;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "upload_file")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UploadFile extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * 스토리지에 업로드된 파일의 공개 URL.
     * 스토리지 연동 전에는 객체가 생성되지 않으므로 컬럼 값은 항상 비어 있다.
     */
    @Column(length = 1024)
    private String url;

    // TODO: 스토리지 연동 시 originalName, storedName 등 파일 메타데이터 필드를 정의한다.
}
