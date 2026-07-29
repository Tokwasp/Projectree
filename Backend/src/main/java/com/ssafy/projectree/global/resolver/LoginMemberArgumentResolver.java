package com.ssafy.projectree.global.resolver;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.exception.BusinessException;
import com.ssafy.projectree.global.exception.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.core.MethodParameter;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;

@Component
public class LoginMemberArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {

        return parameter.hasParameterAnnotation(Login.class)
                && parameter.getParameterType().equals(LoginMember.class);
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest webRequest,
            WebDataBinderFactory binderFactory
    ) {

        HttpServletRequest request =
                webRequest.getNativeRequest(HttpServletRequest.class);

        HttpSession session = request.getSession(false);

        if (session == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }

        LoginMember loginMember =
                (LoginMember) session.getAttribute(SESSION_LOGIN_MEMBER);

        if (loginMember == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }

        return loginMember;
    }
}
