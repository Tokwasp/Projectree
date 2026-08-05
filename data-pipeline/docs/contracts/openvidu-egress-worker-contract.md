# OpenVidu egress → Python Worker 수신 계약

> Legacy compatibility contract. 현재 제품 경로는 [Meeting Analysis Command Join v1](meeting-analysis-command-join-v1.md)을 사용한다. 이 문서의 장시간 Worker 경로는 `ENABLE_LEGACY_OPENVIDU_AUDIO_WORKER=true`와 bucket을 모두 명시한 경우에만 활성화된다.

**Contract version**: `openvidu-egress/1.0`
**작성일**: 2026-07-31
**상태**: 구현 완료. 단, **projectId 매핑 미해결**과 **IAM 권한 부족**으로 실제 E2E는 미완료.
**선행 문서**: [`sqs-message-contract-comparison.md`](./sqs-message-contract-comparison.md)

---

## 1. 실제 OpenVidu egress 메시지

운영 큐 `muOpenviduQueue`에서 실측한 body다 (식별자 마스킹, 4건 모두 동일 구조, 241 bytes).

```json
{
  "roomName": "eebcfd55-****-****-****-************",
  "memberId": null,
  "kind": "MIXED",
  "objectKey": "meetings/eebcfd55-****-****-****-************/mixed/2026-07-31T072730.ogg",
  "egressId": "EG_Uuu*********",
  "endedAt": "2026-07-31T07:28:05.804108359"
}
```

`MessageAttributes`는 `null`이다. 모든 정보가 body에만 있다.

---

## 2. OpenVidu DTO

`data_pipeline/worker/openvidu_events.py`

```python
@dataclass(frozen=True)
class OpenViduEgressEvent:
    room_name: str
    object_key: str
    egress_id: str
    kind: str
    member_id: str | None
    ended_at_raw: str | None      # 파싱하지 않고 원문 문자열로만 보존

    @property
    def filename(self) -> str: ...   # object_key의 마지막 세그먼트
```

**관측된 필드만 모델링했다.** 관측되지 않은 필드는 추가하지 않았다.

---

## 3. 필수 필드 및 검증 규칙

`OpenViduEgressEventParser`

| # | 규칙 | 위반 시 |
|---|---|---|
| 1 | body가 valid JSON | `OpenViduEventValidationError: not valid JSON` |
| 2 | 최상위가 JSON object | `must be a JSON object` |
| 3 | `roomName`이 비어있지 않은 문자열, **128자 이하** | `has no roomName` / `roomName is too long` |
| 4 | `egressId`가 비어있지 않은 문자열, **128자 이하** | `has no egressId` / `egressId is too long` |
| 5 | `objectKey`가 비어있지 않은 문자열, 1024자 이하 | `has no objectKey` |
| 6 | `kind`가 지원 목록에 포함 | `kind is not supported: <값>` |
| 7 | `memberId`는 비어있지 않은 문자열 또는 `null` | `must be a non-empty string or null` |
| 8 | `endedAt`은 문자열 또는 부재 | `must be a string when present` |
| 9 | `objectKey`에 역슬래시 없음 | `must not contain a backslash` |
| 10 | `objectKey`에 빈/`.`/`..` 세그먼트 없음 | `must not contain empty or relative path segments` |
| 11 | `objectKey`가 설정된 prefix 하위 | `outside the configured recording prefix` |
| 12 | prefix 아래에 객체 이름 존재 | `has no object name under the prefix` |
| 13 | **`objectKey`의 room 세그먼트 == `roomName`** | `room segment does not match roomName` |
| 14 | 확장자가 허용 목록에 포함 | `has a disallowed audio extension` |

### 규칙 13 — 교차 room 혼입 방지 (코드 리뷰에서 발견)

projectId/meetingId는 **`roomName`**으로 해석하지만, 실제 음성은 **`objectKey`**에서 가져온다.
둘이 어긋나면 **A방의 프로젝트에 B방의 녹음이 기록된다.** projectId를 지어내지는 않지만
진짜 projectId를 잘못된 녹음에 붙이는 결과라 더 위험하다.

```text
roomName  = ROOM-A
objectKey = meetings/ROOM-B/mixed/x.ogg   → 거부
```

producer는 항상 둘을 같게 보내므로(실측 4건 + 재관측 10건 전부 일치), 불일치는 손상되었거나
위조된 메시지를 뜻한다. 큐가 공유되고 있어 producer를 단일 신뢰 주체로 볼 수 없으므로 강제한다.

### 규칙 3·4 — 128자 상한 (코드 리뷰에서 발견)

`egressId`는 `audio_upload_event.upload_id`(`String(128)`)에 저장된다. 상한이 없으면
**Clova와 LLM 비용을 다 치른 뒤 COMMIT 시점에** PostgreSQL `DataError`가 난다.
SQLite는 길이를 강제하지 않아 테스트로 잡히지 않는다. 기존 `s3_events.py`도 동일하게 128을 강제한다.

### 경로 검증 주의사항 (구현 중 발견한 결함)

검증은 **원문 문자열을 `/`로 split한 결과**에 대해 수행한다. `PurePosixPath`를 쓰면 안 된다.

```text
PurePosixPath("meetings/r/./mixed/a.ogg").parts
  → ('meetings', 'r', 'mixed', 'a.ogg')     # "." 이 사라짐
```

그러나 S3는 `a/./b`와 `a/b`를 **서로 다른 key**로 취급한다. 정규화된 뷰로 검증하면
"검증한 key"와 "실제로 가져오는 key"가 달라진다. 이 결함은 테스트
`test_parser_rejects_path_traversal_and_empty_names`가 먼저 실패시켜 잡아냈고, 그 뒤 수정했다.

---

## 4. 지원 kind

```text
기본 지원: MIXED
```

- 운영에서 관측된 값은 `MIXED` 뿐이다.
- 그 외 값은 **추측하지 않고 명시적으로 거부**한다 (`OpenViduEventValidationError`).
- 거부 동작은 `test_parser_rejects_unsupported_kind`로 고정했다.
- 확장은 `OPENVIDU_SUPPORTED_KINDS` 환경변수로 가능하나, 개별 트랙(`memberId` 채워짐)을
  STT 대상으로 삼을지는 **제품 결정이 필요**하므로 기본값을 넓히지 않았다.

---

## 5. S3 메타데이터 보완

OpenVidu 메시지에 없는 값은 다음 출처에서 채운다. `data_pipeline/worker/openvidu_ingest.py`

| 값 | 출처 |
|---|---|
| `bucket` | 환경변수 `OPENVIDU_RECORDING_BUCKET` |
| `object_key` | 메시지의 `objectKey` (그대로. **복사하지 않는다**) |
| `size` | `HeadObject` → `ContentLength` |
| `etag` | `HeadObject` → `ETag` (따옴표 제거) |
| `version_id` | `HeadObject` → `VersionId` (있으면 우선) |
| `project_id` | `MeetingContextResolver` |
| `external_meeting_id` | `MeetingContextResolver` |
| `upload_id` | `egressId` |
| `filename` | `objectKey` 마지막 세그먼트 |

### HeadObject 결과 검증

- `ContentLength`가 양의 정수인지 (bool 배제)
- `S3_MAX_AUDIO_BYTES` 이하인지
- `VersionId` 또는 `ETag` 중 **최소 하나** 존재 — 없으면 `S3MetadataError`
  (멱등성 키를 만들 수 없으므로 진행 불가)
- 실제 다운로드 후 크기 일치 / eTag MD5 / OGG 매직 바이트 검증은
  기존 `S3TemporaryDownloader`가 그대로 수행한다.

### 실행 순서 (중요)

**매핑 해석이 HeadObject보다 먼저 실행된다.** 그래프에 배치할 수 없는 녹화에
S3 호출 비용을 쓰지 않기 위해서다. `test_unresolved_mapping_is_detected_before_calling_s3`로 고정.

### 파일 복사 없음

`meetings/` 객체를 `audio-input/`으로 복사하지 않는다. 객체 중복·비용·복사 실패 처리·
ETag 변경·정리 정책·지연을 피하기 위해서다. OpenVidu parser는 `meetings/` 계약을 별도로
검증하고, 기존 S3 Event parser의 `audio-input/...` 계약은 **그대로 유지**된다.

---

## 6. roomName 매핑 — 미해결

### 조사 결과 (코드 근거)

| 질문 | 답 |
|---|---|
| `roomName` == 내부 meetingId? | **확정 불가.** 내부 meeting 식별자라는 것이 애초에 존재하지 않는다 |
| `projectId`를 어디서 얻는가? | **얻을 곳이 없다** |

근거:

- Spring Backend 전체에 `meeting`, `room`, `openvidu`, `egress`, `livekit`, `roomName`,
  `UUID` 문자열이 **0건**이다. meeting/room 엔티티도, room 생성 코드도 없다.
- Spring 엔드포인트는 4개뿐이며 room/meeting 조회 API가 없다.
- Frontend 디렉터리에는 `fe.txt`(10 bytes) 하나뿐이다. room↔project를 묶을 코드가 없다.
- Python은 MySQL 드라이버도, Spring 호출 HTTP 클라이언트도 없다.
- Python `meeting` 테이블에는 `room_name` 컬럼이 없고,
  UNIQUE는 `(project_id, external_meeting_id)`라서 `external_meeting_id` 단독으로는
  유일하지 않다. 게다가 행은 파이프라인 자신이 삽입하므로 **최초 수집 시에는 순환**이다.
- **추가 불일치**: Spring `Project.id`는 `int` auto-increment인데
  (`Backend/.../project/entity/Project.java:16-18`), 파이프라인 `project_id`는 실제로
  UUID 문자열을 담고 있다. 매핑 설계 시 이 타입 차이를 먼저 정해야 한다.

### 설계: 포트만 제공

`data_pipeline/worker/meeting_context.py`

```python
class MeetingContextResolver(Protocol):
    def resolve_by_openvidu_room(self, room_name: str) -> MeetingContext | None: ...
```

| 구현체 | 용도 |
|---|---|
| `UnavailableMeetingContextResolver` | **기본값.** 항상 `MeetingContextUnresolvedError`. 매핑 없이 처리되는 일을 원천 차단 |
| `StaticMeetingContextResolver` | 운영자가 명시적으로 제공한 매핑. 통제된 smoke test와 단위 테스트용 |

**의도적으로 제공하지 않은 것**: `roomName`을 그대로 `projectId`로 쓰거나 추측하는 구현.
그런 구현은 회의를 조용히 잘못된 프로젝트에 기록한다. 기본값이 소리내어 실패하는 편이 낫다.
`test_default_resolver_refuses_to_guess`로 고정했다.

---

## 7. 멱등성

**새 migration 없이** 기존 제약을 그대로 재사용한다.

```text
UNIQUE (bucket, object_key, object_identity)   -- uq_audio_upload_object_identity
object_identity = version_id (있으면) else etag
```

| 값 | OpenVidu 경로에서의 내용 |
|---|---|
| `bucket` | `OPENVIDU_RECORDING_BUCKET` |
| `object_key` | `meetings/<roomName>/mixed/<ts>.ogg` |
| `object_identity` | HeadObject의 `VersionId` 또는 `ETag` |
| `upload_id` | **`egressId`** — 녹화 작업 단위로 안정적이며, 별도 컬럼 없이 추적값을 보존한다 |

`egressId`를 `upload_id`(varchar(128))에 넣음으로써 **migration을 추가하지 않고** egress 추적이 가능하다.

동일 메시지 재전달 시 동작(`test_duplicate_openvidu_message_is_idempotent`로 검증):

| 항목 | 결과 |
|---|---|
| S3 다운로드 | 1회만 (`download_calls == 1`) |
| Clova STT | 재호출 없음 |
| LLM | 재호출 없음 |
| `audio_upload_event` | 1행 |
| `request` | 1행 |
| 메시지 | 두 번 모두 삭제 (2번째는 idempotent ACK) |

---

## 8. 오류 분류

`data_pipeline/worker/errors.py` — 모두 `IngestionError` 하위.

| 예외 | 의미 | 메시지 삭제? |
|---|---|:---:|
| `S3EventValidationError` | S3 이벤트 계약 위반 | ❌ |
| `OpenViduEventValidationError` | OpenVidu 계약 위반 (필드 누락, kind 미지원, 경로 위반 등) | ❌ |
| `UnsupportedMessageError` | 어떤 계약에도 해당하지 않음 / OpenVidu 미설정 | ❌ |
| `MeetingContextUnresolvedError` | room → project/meeting 매핑 없음 | ❌ |
| `S3MetadataError` | HeadObject 실패, 크기 초과, identity 없음 | ❌ |
| `S3DownloadError` | 다운로드/검증 실패 | ❌ |
| `UploadAlreadyProcessing` | 다른 워커가 처리 중 | ❌ |
| `PipelineProcessingError` | 파이프라인이 durable 성공에 도달 못함 | ❌ |

**성공했을 때만 `DeleteMessage`를 호출한다.** 실패는 예외 없이 전부 메시지를 큐에 남긴다.

로그는 어떤 계약이 거부했는지 알 수 있도록 `message_id`와 `error_type`을 남기며,
**body는 절대 로그에 남기지 않는다** (회의 내용을 참조할 수 있으므로).
라우터의 미지원 메시지 로그는 **최상위 key 이름만** 남기고 값은 남기지 않는다.

---

## 9. S3 Event 계약과의 공존

`data_pipeline/worker/message_router.py`

```text
body가 JSON이 아님
  → UnsupportedMessageError

"Records" 존재  또는  Event == "s3:TestEvent"
  → 기존 S3EventParser            (contract = "s3-object-created")

roomName + objectKey + egressId 모두 존재
  → OpenViduEgressEventParser     (contract = "openvidu-egress")
     ↳ OpenVidu 미설정이면 UnsupportedMessageError

그 외
  → UnsupportedMessageError (관측된 최상위 key 이름 포함)
```

두 경로 모두 최종적으로 동일한 `S3ObjectRecord`를 만들어낸다. 따라서 다운로더,
`audio_upload_event` claim/멱등성, 파이프라인 실행기는 **변경 없이 재사용**된다.

기존 동작 보존:

- `SqsAudioWorker(parser=...)`만 넘기면 라우터가 S3 전용으로 자동 구성되어
  **OpenVidu 지원 추가 전과 완전히 동일하게** 동작한다.
- 기존 `tests/test_s3_sqs_worker.py` 12개, `tests/test_worker_message_contract.py` 6개
  모두 수정 없이 통과한다.
- OpenVidu 수집은 **opt-in**이다. `OPENVIDU_RECORDING_BUCKET`이 비어 있으면 비활성이다.

---

## 10. 계약 버전 정책

```text
openvidu-egress/1.0   (현재)
```

- **하위 호환 변경** (선택 필드 추가, 새 `kind` 지원): minor 증가.
- **비호환 변경** (필드 제거/의미 변경, prefix 규약 변경): major 증가.
- 라우터 판별자(`roomName` + `objectKey` + `egressId`)는 major 경계 없이 바꾸지 않는다.
- 새 `kind`를 지원할 때는 **실제 관측 샘플을 먼저 확보**하고, 테스트로 고정한 뒤 추가한다.
  관측 없이 추측으로 넓히지 않는다.

---

## 11. 설정

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `OPENVIDU_RECORDING_BUCKET` | *(빈 값)* | 녹화 버킷. **비어 있으면 OpenVidu 수집 비활성** |
| `OPENVIDU_RECORDING_PREFIX` | `meetings/` | 허용 prefix. 자동으로 `/` 보정 |
| `OPENVIDU_SUPPORTED_KINDS` | `MIXED` | CSV |

기존 `S3_ALLOWED_EXTENSIONS`와 `S3_MAX_AUDIO_BYTES`를 그대로 공유한다.

> `.env.example`은 사용자 변경분이 있어 수정하지 않았다. 위 3개 변수를 추가하는 것을 권장한다.

---

## 12. 남은 작업

1. **`MeetingContextResolver` 운영 구현체** — Spring 담당자와 매핑 데이터 소스 확정 후.
2. **IAM 정책 확장** — `meetings/*`에 `s3:GetObject`. 상세는
   [`openvidu-egress-aws-requirements.md`](../operations/openvidu-egress-aws-requirements.md).
3. **DLQ 설정** — 현재 없음.
4. `Project.id` int ↔ UUID 타입 정합 결정.
