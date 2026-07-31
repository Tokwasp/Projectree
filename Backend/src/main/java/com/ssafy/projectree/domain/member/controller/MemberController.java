package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.domain.member.controller.response.MemberProfileResponse;
import com.ssafy.projectree.domain.member.service.MemberService;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/members")
public class MemberController {

    private final MemberService memberService;

    @GetMapping("/me")
    public ResponseEntity<ApiResponse<MemberProfileResponse>> findMyProfile(
            @Login LoginMember loginMember
    ) {
        MemberProfileResponse response = memberService.findProfile(loginMember.getId());
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<MemberSearchResponse>> findByEmail(
            @RequestParam String email,
            @Login LoginMember loginMember
    ) {
        MemberSearchResponse response = memberService.findByEmail(email);
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
