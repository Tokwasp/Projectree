package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.request.NaverLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.NaverLoginResponse;
import com.ssafy.projectree.domain.member.service.AuthService;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    @PostMapping("/google")
    public ResponseEntity<ApiResponse<GoogleLoginResponse>> googleLogin(
            @Valid @RequestBody GoogleLoginRequest request,
            HttpSession session) {

        GoogleLoginResponse response = authService.googleLogin(request, session);
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @PostMapping("/naver")
    public ResponseEntity<ApiResponse<NaverLoginResponse>> naverLogin(
            @Valid @RequestBody NaverLoginRequest request,
            HttpSession session) {

        NaverLoginResponse response = authService.naverLogin(request, session);
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
