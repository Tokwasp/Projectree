package com.ssafy.projectree.domain.member;

import com.ssafy.projectree.domain.uploadfile.UploadFile;
import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Member extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false, length = 50)
    private String name;

    @Column(nullable = false)
    private boolean isDeleted;

    @OneToOne(fetch = FetchType.LAZY, cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumn(name = "upload_file_id")
    private UploadFile uploadFile;

    @Builder
    public Member(String email, String name) {
        this.email = email;
        this.name = name;
    }

    /**
     * 프로필 이미지를 등록하지 않은 회원과 스토리지 연동 전 회원은 모두 URL이 없는 것으로 취급한다.
     * 호출자는 uploadFile의 null 여부를 알 필요 없이 회원을 통해 접근한다.
     */
    public String getProfileImageUrl() {
        if (uploadFile == null) {
            return null;
        }
        return uploadFile.getUrl();
    }

    public void delete() {
        this.isDeleted = true;
    }
}
