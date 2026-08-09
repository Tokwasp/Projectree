## 📌 작업 목적

<!-- 왜 이 작업을 하는지 작성해주세요. -->

- 로그인 API만 있고 로그아웃이 없어서 클라이언트가 세션을 종료할 방법이 없었음
- 세션은 Redis에 저장되므로 클라이언트가 쿠키를 버려도 서버 세션은 TTL까지 그대로 유효하다.
  서버에서 명시적으로 세션을 제거해야 함

---

## 🛠️ 작업 내용

<!-- 주요 변경 사항을 작성해주세요. -->

- 로그아웃 API 추가 (`POST /api/auth/logout`)
    - `session.invalidate()` 로 서버 세션을 제거
    - `@Login` 을 붙여 로그인 상태에서만 호출 가능. 비로그인 요청은
      `LoginMemberArgumentResolver` 가 `UNAUTHORIZED`(401)로 막는다
    - DB 접근이 없어 `AuthService` 를 거치지 않고 컨트롤러에서 세션만 정리

---

## ✅ 테스트

<!-- 테스트한 내용을 작성해주세요. -->

- [x] 빌드 성공
- [x] 기능 테스트 완료

### 테스트 내용

- `AuthControllerTest` 3건 추가
    - 로그인 세션으로 로그아웃하면 200 + 세션이 무효화된다 (`MockHttpSession.isInvalid()` 로 확인)
    - 세션 없이 요청하면 401
    - 세션은 있지만 로그인 정보가 없으면 401 + 세션을 무효화하지 않는다
- 세션 무효화 단정이 실제로 동작을 잡는지 확인하려고 `session.invalidate()` 를 일시 제거해
  해당 테스트만 실패하는 것을 확인한 뒤 원복했다
- `./gradlew test` : 578건 중 576건 통과.
  실패 2건은 `GraphQueryServiceIntegrationTest` 이며 **이번 변경과 무관한 기존 실패**다.
  카테고리 루트 개수를 7로 기대하는데 `Category` enum 값이 6개라서 깨진다
  (`ownerAndMemberCanReadActiveTreeWhileOutsiderIsRejectedBeforeNodeLookup`,
  `returnsVersionZeroAndEmptyTreeWhenGraphSyncDoesNotExist`)

---

## 💬 리뷰 시 확인 부탁드립니다

- **이미 만료된 세션으로 로그아웃하면 401이 응답된다.** `@Login` 을 붙였기 때문인데,
  프론트에서는 "로그아웃 눌렀는데 401" 이 되므로 401도 성공으로 취급해 로그인 화면으로 보내야 한다.
  로그아웃을 멱등하게(세션이 없어도 200) 만드는 편이 나을지 의견 주시면 반영하겠습니다.
