# 프로젝트 가이드

Spring Boot 3 + Java 21 + Gradle 기반 애플리케이션.
도메인형 패키지 구조를 사용한다.

## 명령어

| 목적 | 명령 |
|---|---|
| 전체 빌드 | `./gradlew build` |
| 전체 테스트 | `./gradlew test` |
| 단일 테스트 | `./gradlew test --tests "*OrderServiceTest*"` |
| 애플리케이션 실행 | `./gradlew bootRun` |
| 컴파일만 확인 | `./gradlew compileJava` |

> 위 명령은 실제 프로젝트에 맞게 수정할 것. (Spotless/Checkstyle 등을 쓰면 여기에 추가)

## 패키지 구조

```
com.ssafy.projectree
├── global/              # 도메인 공통. 여기에 비즈니스 로직을 두지 않는다
│   ├── config/
│   └── exception/       # BusinessException, ErrorCode, GlobalExceptionHandler
└── {domain}/            # order, member, product ...
    ├── controller/
    ├── service/
    ├── dto/
    │   ├── request/     # HTTP 요청 바디
    │   └── response/    # HTTP 응답 바디
    ├── entity/
    └── repository/
```

핵심 원칙: **도메인 간 참조는 Service를 통해서만.** 다른 도메인의 Repository나 Entity를
직접 import 하지 않는다. (`order` 패키지에서 `MemberRepository` 직접 호출 금지)

## 작업 규칙

- 코드를 작성/수정하기 전에 해당 레이어의 컨벤션 문서를 **반드시 먼저 읽는다.**
  - Controller → `.claude/docs/conventions/controller.md`
  - Service → `.claude/docs/conventions/service.md`
  - Entity / Repository → `.claude/docs/conventions/entity.md`
  - Request/Response DTO → `.claude/docs/conventions/dto.md`
  - 예외 처리 → `.claude/docs/conventions/exception.md`
  - 테스트 → `.claude/docs/conventions/test.md`
- 전체 구조나 도메인 경계가 헷갈리면 `.claude/docs/architecture.md`를 읽는다.
- 기능 구현 전 `.claude/plans` 에 해당 작업 플랜이 있으면 먼저 읽고 그대로 따른다.
- 새 코드를 짜기 전에 **기존 유사 코드를 먼저 찾아본다.** 컨벤션 문서보다 실제 코드가 우선.
- 변경 후에는 관련 테스트를 실행해서 통과를 확인한 뒤 보고한다.
- 계획에 없던 리팩토링, 라이브러리 추가, 스키마 변경은 먼저 물어본다.

## 하지 말 것

- Entity를 Controller 응답으로 그대로 반환
- 필드 주입(`@Autowired` 필드) 사용
- 테스트 없이 새 비즈니스 로직 추가
- `git commit` / `git push` 를 사용자 지시 없이 실행
- 실패하는 테스트를 `@Disabled` 로 덮기
