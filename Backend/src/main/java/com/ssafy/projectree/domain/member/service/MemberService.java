package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
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
}
