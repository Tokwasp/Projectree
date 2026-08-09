# 회의록 상세 조회 API (프론트엔드)

회의록 본문과 추정 회의 시간을 함께 반환한다.
회의록은 Python 분석 서버의 Callback으로 최초 생성되며(`meeting-record-callback.md` 참고),
이 API는 저장된 회의록을 읽기만 한다.

## Endpoint

```
GET /api/projects/{projectId}/meetings/{meetingId}/record
```

## 인증과 권한

- **로그인 필수.** 세션 쿠키(`SESSION`)로 인증한다.
- **해당 프로젝트의 멤버만 조회할 수 있다.** 역할(OWNER/MEMBER) 구분은 없다.
- 프로젝트 멤버 검증은 회의·회의록 조회보다 **먼저** 수행된다.
  비멤버가 `meetingId`를 바꿔가며 회의록 존재 여부를 탐색할 수 없도록 하기 위함이다.
  따라서 비멤버에게는 회의록이 없더라도 `MEETING_RECORD_NOT_FOUND`가 아니라
  `PROJECT_PARTICIPANT_NOT_FOUND`가 반환된다.

## 성공 응답 — `200 OK`

```json
{
  "status": 200,
  "message": "성공",
  "data": {
    "meetingRecordId": 12,
    "projectId": 3,
    "meetingId": 35,
    "title": "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의",
    "meetingDate": "2026-08-05",
    "startedAt": "2026-08-05T15:00:00",
    "endedAt": "2026-08-05T16:31:00",
    "durationMinutes": 91,
    "summary": ["회의록 자동 생성 품질을 검토했습니다."],
    "decisions": ["CI/CD 파이프라인을 단순화하기로 했습니다."],
    "nextTodos": ["기술 용어 사전 목록을 설계합니다."],
    "issues": ["전문 용어 변환 오류가 있습니다."],
    "version": 0,
    "createdAt": "2026-08-05T16:35:00",
    "updatedAt": "2026-08-05T16:35:00"
  }
}
```

### 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `meetingRecordId` | long | 회의록 식별자 |
| `projectId` / `meetingId` | int | 요청 경로의 식별자 |
| `title` | string | 회의록 제목 (최대 200자) |
| `meetingDate` | date | `startedAt`의 날짜 부분 |
| `startedAt` / `endedAt` | date-time | **추정값** (아래 참고) |
| `durationMinutes` | long | 추정 진행 시간(분). 항상 0 이상 |
| `summary` | string 배열 | 전체 요약 항목 |
| `decisions` | string 배열 | 결정 사항 |
| `nextTodos` | string 배열 | 다음 할 일 |
| `issues` | string 배열 | 이슈 |
| `version` | long | 낙관적 락 버전 |
| `createdAt` / `updatedAt` | date-time | 회의록 생성·수정 시각 |

### 본문 배열의 의미

- 네 영역은 **항상 배열**이다. 비어 있으면 `null`이 아니라 `[]`를 반환한다.
- **저장된 순서를 그대로 유지한다.** 프론트는 받은 순서대로 렌더링하면 된다.
- 각 항목은 공백이 아닌 문자열이다.

### `version` 의미

회의록의 낙관적 락 버전이다. 최초 생성 시 `0`이며 사용자가 회의록을 수정할 때마다 증가한다.
Python Callback 재시도로는 증가하지 않는다.

향후 수정 API가 추가되면 이 값을 그대로 되돌려보내 동시 수정 충돌을 감지하는 데 사용한다.
**현재 단계에는 수정 API가 없으므로 표시 및 보관 목적으로만 사용한다.**

## 추정 시간 계산 정책

> **`startedAt`과 `endedAt`은 실제 WebRTC 입·퇴장 시각이 아니라
> Meeting 생성 시각과 분석 요청 확정 시각을 조합한 추정값입니다.**

| 값 | 계산 |
|---|---|
| `startedAt` | `Meeting.createdAt` — Redis 회의방 정보가 Java DB로 동기화된 시각 |
| `endedAt` (1순위) | 회의록의 분석 요청 Command Outbox의 `createdAt` — 생성자가 회의 종료 후 분석 옵션을 확정한 시각 |
| `endedAt` (2순위) | `MeetingRecord.createdAt` — 회의록이 저장된 시각 |
| `endedAt` (최종) | `startedAt`과 동일 |
| `meetingDate` | `startedAt.toLocalDate()` |
| `durationMinutes` | `max(0, endedAt - startedAt)` 의 분 단위 |

**실제 통화 시작·종료 시각과 수 초에서 수 분 차이가 날 수 있다.** 정확한 통화 시간이 필요하면
WebRTC 참여 기록을 저장하는 별도 기능이 추가되어야 한다.

### fallback

> **분석 Command Outbox 정보를 사용할 수 없으면
> 회의록 생성 시각을 종료 추정 시각으로 사용합니다.**

Outbox의 `createdAt`은 다음을 **모두** 만족할 때만 사용한다.

- Outbox 행이 존재한다
- `commandType`이 분석 요청(`MEETING_ANALYSIS_REQUESTED`)이다
- Outbox가 가리키는 회의가 요청한 회의와 같다
- `createdAt`이 존재한다
- `createdAt`이 `startedAt`보다 빠르지 않다

하나라도 어긋나면 `MeetingRecord.createdAt`으로, 그마저도 쓸 수 없으면 `startedAt`으로 대체한다.
**이 경우에도 조회는 실패하지 않는다.** 회의록 조회가 Outbox 영구 보존에 종속되지 않도록 한 결정이다.

## 참여자 목록이 아직 없는 이유

응답에 `participants` 필드는 **포함되지 않는다.**

현재 백엔드에는 실제로 회의에 입장한 사용자를 증명하는 영속 데이터가 없다.
프로젝트 전체 멤버를 회의 참여자로 반환하면 실제로 참석하지 않은 사용자까지
참여자로 표시되어 잘못된 정보를 주게 된다. 회의 생성자 한 명만 반환하는 것도 부정확하다.

참여자 기능은 실제 WebRTC 참여 기록 또는 Redis 회의방 데이터 보존 정책이 확정된 뒤
별도 작업으로 추가한다.

## 오류 응답

| Status | errorCode | 의미 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 로그인하지 않음 |
| 404 | `PROJECT_NOT_FOUND` | 프로젝트가 존재하지 않음 |
| 404 | `PROJECT_PARTICIPANT_NOT_FOUND` | 해당 프로젝트의 멤버가 아님 |
| 404 | `MEETING_NOT_FOUND` | 회의가 존재하지 않음 |
| 400 | `MEETING_PROJECT_MISMATCH` | 회의가 요청한 프로젝트에 속하지 않음 |
| 404 | `MEETING_RECORD_NOT_FOUND` | 아직 회의록이 생성되지 않음 |
| 500 | `INTERNAL_SERVER_ERROR` | 비정상적으로 `Meeting.createdAt`이 없어 시간을 추정할 수 없는 경우 |

`MEETING_RECORD_NOT_FOUND`는 다음 상황에서 정상적으로 발생할 수 있다.

- 회의 분석을 아직 요청하지 않음
- 요약 생성을 요청하지 않음(`generateSummary = false`)
- 분석이 진행 중이라 Callback이 아직 도착하지 않음
- 분석이 실패로 확정됨

프론트는 이 응답을 오류 화면이 아니라 "회의록이 아직 없음" 상태로 표시하는 것이 자연스럽다.
필요하면 회의의 요약 분석 상태를 함께 조회해 진행 중·실패를 구분한다.

## 참고

- 이 API는 조회만 수행하며 회의 상태나 회의록을 변경하지 않는다.
  비관적 락을 사용하지 않고 read-only 트랜잭션으로 동작한다.
- 내부 식별자인 `commandId`는 응답에 노출하지 않는다.
- 회의록 수정 API는 아직 제공되지 않는다.
