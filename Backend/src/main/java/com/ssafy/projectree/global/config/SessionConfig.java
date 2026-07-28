package com.ssafy.projectree.global.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;
import tools.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import tools.jackson.databind.jsontype.PolymorphicTypeValidator;

@Configuration
public class SessionConfig {

    private static final String SESSION_COOKIE_NAME = "SESSION";
    private static final String SESSION_COOKIE_PATH = "/";

    private static final String JAVA_LANG_PACKAGE = "java.lang.";
    private static final String JAVA_UTIL_PACKAGE = "java.util.";
    private static final String PROJECT_PACKAGE = "com.ssafy.projectree.";

    private final boolean secureCookie;
    private final String sameSite;

    public SessionConfig(
            @Value("${app.session.cookie.secure}") boolean secureCookie,
            @Value("${app.session.cookie.same-site}") String sameSite) {
        this.secureCookie = secureCookie;
        this.sameSite = sameSite;
    }

    @Bean
    public CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName(SESSION_COOKIE_NAME);
        serializer.setCookiePath(SESSION_COOKIE_PATH);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(secureCookie);
        serializer.setSameSite(sameSite);
        return serializer;
    }

    @Bean
    public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return GenericJacksonJsonRedisSerializer.builder()
                .enableDefaultTyping(sessionTypeValidator())
                .build();
    }

    private PolymorphicTypeValidator sessionTypeValidator() {
        return BasicPolymorphicTypeValidator.builder()
                .allowIfBaseType(Object.class)
                .allowIfSubType(JAVA_LANG_PACKAGE)
                .allowIfSubType(JAVA_UTIL_PACKAGE)
                .allowIfSubType(PROJECT_PACKAGE)
                .build();
    }
}
