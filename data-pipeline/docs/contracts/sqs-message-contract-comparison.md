# SQS 메시지 계약 비교 — OpenVidu egress producer ↔ Python Worker parser

**작성일**: 2026-07-31
**작성 목적**: 실제 운영 큐의 producer 메시지와 Python Worker가 기대하는 메시지의 차이를 확정하고,
Spring이 최종적으로 보내야 할 표준 계약안을 도출한다.
**범위**: 조사 전용. **코드는 수정하지 않았다.**

---

## 0. 근거 데이터 출처

이 문서의 OpenVidu 메시지는 **추측이 아니라 실제 AWS SQS 큐에서 수신한 데이터**다.

| 항목 | 값 |
|---|---|
| 큐 | `https://sqs.ap-northeast-2.amazonaws.com/<ACCOUNT>/muOpenviduQueue` |
| 큐 ARN | `arn:aws:sqs:ap-northeast-2:1109****1538:muOpenviduQueue` |
| 관측 방법 | `ReceiveMessage` with `--visibility-timeout 0` (삭제하지 않음) |
| 관측 시각 | 2026-07-31 06:36 UTC, 07:29 UTC (2회) |
| 관측한 서로 다른 메시지 | **4건** — `b72e798c-…`, `e6c9418c-…`, `8f5ced3a-…`, `8853268d-…` (모두 마스킹) |
| body 길이 | 4건 모두 **241 bytes**, 필드 구성 **완전 동일** |
| `MessageAttributes` | **null** (4건 모두) — 메타데이터는 body에만 존재 |
| SQS system attributes | `ApproximateFirstReceiveTimestamp`, `ApproximateReceiveCount`, `SenderId`, `SentTimestamp` |

Worker 측 계약의 근거는 다음 코드와 테스트다.

| 근거 | 위치 |
|---|---|
| parser 본체 | `data_pipeline/worker/s3_events.py` (`S3EventParser.parse`, `_parse_record`) |
| 다운로드 검증 | `data_pipeline/worker/s3_download.py` (`S3TemporaryDownloader.download`) |
| 멱등성 키 | `data_pipeline/worker/uploads.py` (`_event_query`) + `audio_upload_event` UNIQUE 제약 |
| 정상 케이스 테스트 | `tests/test_s3_sqs_worker.py::test_parser_decodes_multiple_records_and_prefers_version_id` |
| 거부 케이스 테스트 | `tests/test_s3_sqs_worker.py::test_parser_rejects_malformed_or_disallowed_events` (8 케이스) |
| 계약 불일치 회귀 테스트 | `tests/test_worker_message_contract.py` |

---

## 1. 실제 OpenVidu egress 메시지 (전체 구조, 마스킹)

### 1-1. 원문 구조

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

> 실제 body는 공백 없는 압축 JSON 한 줄(241 bytes)이다. 위는 가독성을 위해 정렬한 것이며
> 필드 순서와 구성은 원문 그대로다.

### 1-2. 필드별 관측 사실

| 필드 | JSON 타입 | 관측값 특성 |
|---|---|---|
| `roomName` | string | UUID v4 형식. **`objectKey` 경로 2번째 세그먼트와 항상 동일** |
| `memberId` | null | 관측한 4건 모두 `null` (`kind=MIXED`이므로 개별 화자가 없음) |
| `kind` | string | 4건 모두 `"MIXED"`. 개별 트랙 종류가 존재할 가능성이 있으나 **미관측** |
| `objectKey` | string | `meetings/<roomName>/mixed/<yyyy-MM-dd'T'HHmmss>.ogg` 고정 패턴 |
| `egressId` | string | `EG_` + 12자 영숫자. LiveKit/OpenVidu egress job 식별자 |
| `endedAt` | string | **나노초 9자리, 타임존 오프셋 없음** → Java `LocalDateTime.toString()` 형태 |

### 1-3. 관측으로 확인된 추가 사실 (중요)

1. **`bucket`이 메시지 어디에도 없다.** `objectKey`만 있고 어느 버킷인지 알 수 없다.
2. **`projectId`가 메시지 어디에도 없다.** 식별자는 `roomName` / `egressId` 뿐이다.
3. **`endedAt`에 타임존이 없다.** UTC인지 KST인지 메시지만으로 판별 불가.
4. **해당 `objectKey`를 현재 자격증명으로 읽을 수 없다.**
   ```text
   $ aws s3api head-object --bucket projectree-bucket \
       --key "meetings/<roomName>/mixed/<ts>.ogg"
   An error occurred (403) when calling the HeadObject operation: Forbidden
   ```
   같은 자격증명으로 `audio-input/test/...` 는 정상 동작한다. 즉 IAM 정책이
   **`audio-input/*` prefix로 한정**되어 있다.
   `s3:ListBucket` 권한도 없어 **403이 "객체 없음"인지 "권한 없음"인지 구분할 수 없다.**
   → 메시지 계약을 고쳐도 **IAM 정책을 함께 넓히지 않으면 이 구간은 여전히 동작하지 않는다.**

---

## 2. Python Worker가 현재 기대하는 메시지 구조

### 2-1. 기대 JSON (AWS S3 Event Notification 형식)

```json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-northeast-2",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "s3SchemaVersion": "1.0",
        "bucket": { "name": "projectree-bucket" },
        "object": {
          "key": "audio-input/test/<projectId>/<meetingId>/<uploadId>/<filename>.ogg",
          "size": 4964632,
          "eTag": "09d437a78ef9edf3b76e2939d746c2be",
          "versionId": null
        }
      }
    }
  ]
}
```

특수 케이스로 S3 테스트 이벤트만 별도 허용한다 (`parse()` 초입에서 무시하고 ACK).

```json
{ "Service": "Amazon S3", "Event": "s3:TestEvent" }
```

### 2-2. 필수 조건 (parser 코드 기준)

| # | 조건 | 위반 시 예외 메시지 |
|---|---|---|
| 1 | 최상위가 JSON object | `SQS body is not valid JSON` / `S3 event must be a JSON object` |
| 2 | `Records`가 **비어있지 않은 배열** | `S3 event Records must be a non-empty array` |
| 3 | `eventName`이 `ObjectCreated:` 또는 `s3:ObjectCreated:` 로 시작 | `is not an ObjectCreated event` |
| 4 | `s3.bucket.name`이 `S3_ALLOWED_BUCKETS` 에 포함 | `uses a disallowed bucket` |
| 5 | `s3.object.key`가 URL 인코딩(`unquote_plus`로 디코딩됨) | — |
| 6 | 디코딩된 key = `S3_INPUT_PREFIX` + **정확히 4 세그먼트** | `does not match the object key contract` |
| 7 | 경로 탈출 금지 (`..`, `.`, 빈 세그먼트, `\` 불가) | `does not match the object key contract` |
| 8 | 각 식별자 세그먼트 128자 이하, 공백만인 값 금지 | `key identifier is too long` / `has an empty key identifier` |
| 9 | 확장자가 `S3_ALLOWED_EXTENSIONS` 에 포함 | `has a disallowed audio extension` |
| 10 | `s3.object.size`가 **양의 정수** (bool 불가) 이고 `S3_MAX_AUDIO_BYTES` 이하 | `has an invalid object size` / `exceeds the audio size limit` |
| 11 | `versionId` 또는 `eTag` 중 **최소 하나 존재** | `needs versionId or eTag` |

### 2-3. key에서 파생되는 값 (별도 필드가 아니라 경로에서 추출)

```text
S3_INPUT_PREFIX = "audio-input/test/"   (현재 .env 값)

audio-input/test/<projectId>/<meetingId>/<uploadId>/<filename>
                  └ project_id           └ upload_id
                                └ external_meeting_id
                                                    └ filename
```

`_parse_record()` 는 `len(key_parts) != len(prefix_parts) + 4` 이면 거부한다.
현재 prefix가 2 세그먼트이므로 **전체 key는 정확히 6 세그먼트**여야 한다.

> 참고: 테스트(`tests/test_s3_sqs_worker.py`)는 parser 기본값인 `audio-input/`(1 세그먼트)를 쓰므로
> 테스트상의 key는 5 세그먼트다. 런타임 계약은 `.env`의 `S3_INPUT_PREFIX`가 결정한다.

### 2-4. 다운로드 단계의 추가 요구 (`s3_download.py`)

| 검증 | 내용 |
|---|---|
| 크기 일치 | 다운로드 실제 크기 == 메시지의 `size` (불일치 시 실패) |
| eTag 검증 | `versionId`가 없고 `eTag`가 32자 hex이면 **로컬 MD5와 대조** |
| 매직 바이트 | 확장자와 실제 헤더 일치 (`.ogg` → `OggS`) |
| VersionId 사용 | `versionId`가 있으면 `GetObject`에 `VersionId` 전달 |

### 2-5. 멱등성 키

```text
UNIQUE (bucket, object_key, object_identity)      -- uq_audio_upload_object_identity
object_identity = versionId (있으면) else eTag
```

→ **`eTag`와 `versionId`가 둘 다 없으면 중복 방지가 성립하지 않는다.** 이는 선택 필드가 아니다.

---

## 3. 필드별 비교표

| Worker 필요 값 | OpenVidu 메시지 | 존재 | 비고 |
|---|---|:---:|---|
| `Records[]` 래퍼 | — | ❌ | flat object. S3 이벤트가 아님 |
| `eventName` | — | ❌ | 없음 |
| `s3.bucket.name` | — | ❌ | **버킷 정보 자체가 없음** |
| `s3.object.key` | `objectKey` | △ | 이름은 대응하나 **prefix·세그먼트 수가 계약 위반** |
| ↳ `projectId` (key 1번째) | — | ❌ | **메시지에 전혀 없음. 파생 불가** |
| ↳ `meetingId` (key 2번째) | `roomName` | △ | 값은 있으나 room↔meeting 동일성 확인 필요 |
| ↳ `uploadId` (key 3번째) | — | ❌ | 대응값 없음 (`egressId`가 유사 역할) |
| ↳ `filename` (key 4번째) | `objectKey` 마지막 | ✅ | `2026-07-31T072730.ogg` |
| `s3.object.size` | — | ❌ | 없음 → 사전 크기 제한 검증 불가 |
| `s3.object.eTag` | — | ❌ | 없음 → **멱등성 키 생성 불가** |
| `s3.object.versionId` | — | ❌ | 없음 |
| (미사용) | `kind` | ✅ | Worker 미사용 |
| (미사용) | `memberId` | ✅ | Worker 미사용 (항상 null) |
| (미사용) | `egressId` | ✅ | Worker 미사용 |
| (미사용) | `endedAt` | ✅ | Worker 미사용 |

### 3-1. key 구조 비교

```text
OpenVidu :  meetings / <roomName>  / mixed      / <ts>.ogg          → 4 세그먼트
Worker   :  audio-input / test / <projectId> / <meetingId> / <uploadId> / <file>.ogg  → 6 세그먼트
            └──── S3_INPUT_PREFIX ────┘
```

prefix도 다르고 세그먼트 수도 다르다. **`objectKey` 값을 그대로 재사용할 수 없다.**

### 3-2. 종합 판정

OpenVidu 메시지는 Worker의 **필수 조건 11개 중 1번(JSON object)만 통과**하고 2번에서 즉시 거부된다.

```text
S3EventValidationError: S3 event Records must be a non-empty array
```

이는 실제 Worker 실행 로그로 4회 재현했고, 회귀 테스트
`tests/test_worker_message_contract.py::test_openvidu_egress_body_is_rejected_by_the_s3_event_parser`
로 고정해 두었다.

---

## 4. 필드 분류

### 4-A. 이름만 변환하면 되는 필드

| OpenVidu | → 표준 계약 | 비고 |
|---|---|---|
| `roomName` | `meetingId` | 값 그대로 사용 가능. **단, "OpenVidu room 1건 = meeting 1건"이 성립하는지 팀 확인 필요.** 확인되지 않으면 4-B로 이동 |
| `objectKey`의 마지막 세그먼트 | `fileName` | `2026-07-31T072730.ogg` 그대로 사용 가능 |

> `objectKey` 전체는 **이름 변환만으로 해결되지 않는다.** prefix와 세그먼트 수가 달라
> 4-D(새로 생성)에 해당한다.

### 4-B. Spring DB 조회로 보완해야 하는 필드

| 필드 | 조회 근거 | 중요도 |
|---|---|---|
| `projectId` | `roomName`(또는 meeting) → **project 매핑을 Spring DB에서 조회** | **필수 / 최우선.** 메시지·S3·파일명 어디에서도 파생 불가. 이 값이 없으면 Worker는 그래프에 저장할 위치를 결정할 수 없다 |
| `meetingId` (정규화) | `roomName`이 외부 room 식별자라면 내부 meeting 식별자로 변환 | room↔meeting이 1:1이 아니면 필수 |

### 4-C. S3 업로드 결과에서 가져와야 하는 필드

Spring이 `PutObject` 응답 또는 `HeadObject` 호출로 확보한다.

| 필드 | 출처 | 필수 여부 |
|---|---|---|
| `bucket` | 업로드 대상 버킷명 (Spring 설정) | **필수** |
| `sizeBytes` | `HeadObject` → `ContentLength` | **필수** (크기 제한 사전 검증) |
| `eTag` | `PutObject` 응답 `ETag` 또는 `HeadObject` → `ETag` | **필수** (멱등성 키) |
| `versionId` | 버저닝 활성 시 `PutObject` 응답 `VersionId` | 선택 (있으면 eTag보다 우선) |
| `contentType` | `HeadObject` → `ContentType` | 선택 (Worker 미사용, 계약 명료성용) |

> 실측 예시 (`audio-input/test/...` 업로드):
> `ETag "09d437a78ef9edf3b76e2939d746c2be"`, `ContentLength 4964632`, `ContentType audio/ogg`.
> eTag는 따옴표로 감싸여 오므로 **Spring이 따옴표를 제거해 보내는 것을 권장**한다
> (Worker도 `strip('"')` 하지만 계약을 명확히 하는 편이 낫다).

### 4-D. 새로 생성해야 하는 필드

| 필드 | 생성 방법 |
|---|---|
| `key` | **새 규약으로 재구성.** `audio-input/test/<projectId>/<meetingId>/<uploadId>/<fileName>` — 기존 `meetings/...` key는 계약 위반이므로 그대로 못 씀 |
| `uploadId` | 업로드 건별 신규 UUID (재시도와 재업로드를 구분하는 단위) |
| `jobId` | 처리 작업 신규 UUID (로그 상관관계 추적용) |
| `schemaVersion` | 상수 `"1.0"` |
| `createdAt` | 업로드 완료 시각, **ISO-8601 + 타임존 오프셋 필수** |
| (S3 event 흉내 시) `Records[]`, `eventName`, `eventSource` | 표준 S3 이벤트 봉투 |

### 4-E. 사용하지 않아도 되는 OpenVidu 필드

| 필드 | 사유 |
|---|---|
| `egressId` | Worker 미사용. **추적용 메타로 남기는 것은 권장** (녹화 작업 역추적) |
| `kind` | Worker 미사용. Spring이 `MIXED`만 처리하도록 **필터 조건으로 쓰고 전달은 불필요** |
| `memberId` | 관측상 항상 `null`. 화자 분리는 Clova STT가 수행 |
| `endedAt` | Worker 미사용. 타임존이 없어 그대로 쓰기 위험. `createdAt`으로 대체 |

---

## 5. Spring이 최종적으로 전송해야 할 표준 JSON 계약안

두 가지 안을 제시한다. **안 1이 권장안**이고, **안 2는 Worker를 전혀 고치지 않고 지금 당장 쓸 수 있는 안**이다.

### 안 1 (권장) — 전용 계약

```json
{
  "schemaVersion": "1.0",
  "jobId": "3f1c9a2e-0d44-4a1b-9c77-2b6e8a5d1f30",
  "projectId": "168a9037-485a-4145-a93f-a651fd1a254c",
  "meetingId": "33cdf33c-aa42-471e-a0a0-d257ffc8a9eb",
  "uploadId": "a7c21b90-5e3d-4f88-b012-77c9de4a3311",
  "bucket": "projectree-bucket",
  "key": "audio-input/test/168a9037-485a-4145-a93f-a651fd1a254c/33cdf33c-aa42-471e-a0a0-d257ffc8a9eb/a7c21b90-5e3d-4f88-b012-77c9de4a3311/2026-07-31T072730.ogg",
  "fileName": "2026-07-31T072730.ogg",
  "contentType": "audio/ogg",
  "sizeBytes": 4964632,
  "eTag": "09d437a78ef9edf3b76e2939d746c2be",
  "versionId": null,
  "createdAt": "2026-07-31T07:28:05.804+09:00",
  "source": {
    "producer": "openvidu-egress",
    "egressId": "EG_UuuCd2jaUU6J",
    "roomName": "eebcfd55-bdd1-4dc0-b0a2-352a072cd3cf",
    "kind": "MIXED"
  }
}
```

**필드 규약**

| 필드 | 타입 | 필수 | 규칙 |
|---|---|:---:|---|
| `schemaVersion` | string | ✅ | `"1.0"` 고정 |
| `jobId` | string(UUID) | ✅ | 요청 단위 신규 생성 |
| `projectId` | string(UUID) | ✅ | **Spring DB 조회 결과** |
| `meetingId` | string(UUID) | ✅ | `roomName` 매핑 또는 DB 조회 |
| `uploadId` | string(UUID) | ✅ | 업로드 건별 신규 생성 |
| `bucket` | string | ✅ | 허용 버킷 |
| `key` | string | ✅ | `audio-input/test/{projectId}/{meetingId}/{uploadId}/{fileName}` |
| `fileName` | string | ✅ | 허용 확장자 |
| `contentType` | string | — | `audio/ogg` 등 |
| `sizeBytes` | number(int) | ✅ | 0 초과, 104857600 이하 |
| `eTag` | string | ✅* | 따옴표 제거. `versionId`가 있으면 선택 |
| `versionId` | string \| null | — | 버저닝 시 |
| `createdAt` | string | ✅ | ISO-8601 **오프셋 포함** |
| `source` | object | — | 추적용. Worker 로직에 영향 없음 |

\* `eTag`와 `versionId` 중 **최소 하나는 반드시 있어야 한다** (멱등성 키).

> **주의**: 안 1을 채택하면 **Worker의 parser 확장이 필요하다.**
> `S3EventParser`는 현재 `Records[]`만 이해한다. 이번 작업에서는 코드를 수정하지 않았으므로,
> 안 1은 아직 Worker가 처리하지 못한다.

### 안 2 (무변경 임시안) — S3 이벤트 형식 그대로 전송

Worker 코드를 전혀 건드리지 않고 **오늘 당장** 동작하는 형식이다.
실제로 이 형식으로 4회 E2E를 성공시켰다.

```json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-northeast-2",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "s3SchemaVersion": "1.0",
        "bucket": { "name": "projectree-bucket" },
        "object": {
          "key": "audio-input/test/168a9037-.../33cdf33c-.../a7c21b90-.../2026-07-31T072730.ogg",
          "size": 4964632,
          "eTag": "09d437a78ef9edf3b76e2939d746c2be"
        }
      }
    }
  ]
}
```

| 장점 | 단점 |
|---|---|
| Worker 코드 변경 0 | Spring이 S3인 척해야 함 (의미상 부정확) |
| 검증된 경로 (E2E 4회 성공) | `jobId`·`createdAt`·추적 메타를 실을 자리가 없음 |
| 즉시 적용 가능 | 모든 식별자를 key 경로에 우겨넣어야 함 |

### 어느 쪽을 택하든 반드시 함께 해결해야 할 것

1. **업로드 위치 변경 또는 prefix 계약 변경**
   현재 녹화 파일은 `meetings/...` 에 저장된다. Worker는 `audio-input/test/...` 만 받는다.
   → Spring이 `audio-input/` 하위로 업로드(또는 복사)하거나, `S3_INPUT_PREFIX`를 재설계해야 한다.
   단, prefix를 `meetings/`로 바꾸면 **세그먼트 수 계약(projectId/meetingId/uploadId/filename)도
   함께 바뀌므로 parser 수정이 필요**하다.

2. **IAM 정책 확장**
   현재 자격증명은 `meetings/` prefix에서 `HeadObject` 403이다.
   Worker가 읽어야 하는 prefix 전체에 `s3:GetObject` 권한이 필요하고,
   운영 진단을 위해 `s3:ListBucket`도 권장한다.

3. **DLQ 설정**
   현재 `RedrivePolicy`가 없어 실패 메시지가 무한 재시도된다.
   계약 전환기에는 실패가 늘어나므로 DLQ가 특히 중요하다.

4. **큐 분리 검토**
   `muOpenviduQueue`는 녹화 서비스와 공용이다. 계약을 바꾸면 기존 소비자와 충돌할 수 있으므로
   파이프라인 전용 큐를 두는 편이 안전하다.

---

## 6. 미해결 질문 (팀 확인 필요)

이 문서는 관측 사실만 기술했다. 다음은 **추측하지 않고 남겨둔 결정 사항**이다.

1. OpenVidu `roomName` 1건은 meeting 1건과 1:1인가? 아니면 한 room에서 여러 meeting이 나올 수 있나?
2. `projectId`는 어느 테이블·어느 컬럼에서 조회하는가? (room → project 경로 정의 필요)
3. `kind`가 `MIXED` 외에 어떤 값을 가지며, 그때 `memberId`가 채워지는가? 개별 트랙도 STT 대상인가?
4. `endedAt`의 타임존은 UTC인가 KST인가? (오프셋이 없어 판별 불가)
5. 녹화 파일을 `audio-input/` 로 옮길 것인가, 아니면 Worker가 `meetings/` 를 받아들이도록 할 것인가?
6. 안 1(전용 계약)과 안 2(S3 이벤트 형식) 중 무엇을 표준으로 삼을 것인가?

---

## 부록 A. 재현 명령

```powershell
$env:AWS_PROFILE="dp-test"

# 실제 producer 메시지 관찰 (삭제하지 않음)
aws sqs receive-message `
  --queue-url "<SQS_QUEUE_URL>" `
  --max-number-of-messages 10 `
  --visibility-timeout 0 `
  --message-system-attribute-names All `
  --message-attribute-names All

# meetings/ prefix 접근 확인 (403 재현)
aws s3api head-object --bucket projectree-bucket `
  --key "meetings/<roomName>/mixed/<timestamp>.ogg"

# 계약 불일치 회귀 테스트
.venv\Scripts\python.exe -m pytest tests/test_worker_message_contract.py -v
```

## 부록 B. 관련 산출물

```text
outputs/aws-e2e/20260731-c12412d8/
├─ final-report.md              # 전체 E2E 실험 보고서
├─ aws-connectivity.json        # 큐/버킷 상태, DLQ 부재
└─ sqs-message-redacted.json    # 실제 발송/수신 메시지 기록
```

---

**본 문서 작성 과정에서 코드 수정, commit, push는 수행하지 않았다.**
