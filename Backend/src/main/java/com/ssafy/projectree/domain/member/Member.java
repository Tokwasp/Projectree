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
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false, length = 50)
    private String name;

    @OneToOne(fetch = FetchType.LAZY, cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumn(name = "upload_file_id")
    private UploadFile uploadFile;

    @Builder
    public Member(String email, String name) {
        this.email = email;
        this.name = name;
    }
}
