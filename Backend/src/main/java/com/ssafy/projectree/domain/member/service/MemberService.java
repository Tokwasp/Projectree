package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.domain.member.controller.response.MemberProfileResponse;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MemberService {

    private final MemberRepository memberRepository;

    public MemberSearchResponse findByEmail(String email) {
        return memberRepository.findByEmail(email)
                .map(MemberSearchResponse::from)
                .orElseThrow(() -> new CustomException(CommonErrorCode.MEMBER_NOT_FOUND));
    }

    /**
     * LoginMember는 로그인 시점의 스냅샷이므로 이후 이름 변경 등의 최신 정보를 반영하지 못한다.
     * 프로필은 항상 최신 값을 보여줘야 하므로 세션 값을 그대로 반환하지 않고 다시 조회한다.
     */
    public MemberProfileResponse findProfile(int memberId) {
        return memberRepository.findById(memberId)
                .map(MemberProfileResponse::from)
                .orElseThrow(() -> new CustomException(CommonErrorCode.MEMBER_NOT_FOUND));
    }
}
