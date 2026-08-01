# OpenVidu egress 수집을 위한 AWS 인프라 요구사항

**작성일**: 2026-07-31
**상태**: 문서화만 수행. **AWS 리소스는 하나도 변경하지 않았다.**
**관련**: [`openvidu-egress-worker-contract.md`](../contracts/openvidu-egress-worker-contract.md)

---

## 0. 요약 — 지금 막혀 있는 것

| # | 차단 요소 | 현재 상태 | 담당 |
|---|---|---|---|
| 1 | `meetings/*` 읽기 권한 | ❌ **403 Forbidden** | 인프라 |
| 2 | room → project 매핑 | ❌ 데이터 소스 없음 | Spring/제품 |
| 3 | DLQ | ❌ 미설정 | 인프라 |

1번이 해결되어도 2번이 남으면 실제 수집은 되지 않는다. 둘은 독립적이다.

---

## 1. S3 IAM 권한

### 현재 실측 상태

Worker가 쓰는 자격증명(`arn:aws:iam::1109****1538:user/test_user`)은
`audio-input/*`에는 접근되지만 `meetings/*`에는 접근되지 않는다.

```powershell
$env:AWS_PROFILE="dp-test"

# 성공
aws s3api head-object --bucket projectree-bucket `
  --key "audio-input/test/<proj>/<meeting>/<upload>/<file>.ogg"

# 실패 — 실측
aws s3api head-object --bucket projectree-bucket `
  --key "meetings/<roomName>/mixed/<timestamp>.ogg"
# An error occurred (403) when calling the HeadObject operation: Forbidden
```

새 adapter 코드 경로로도 동일하게 재현된다.

```text
S3MetadataError: S3 HeadObject failed for the OpenVidu recording
  caused by ClientError: An error occurred (403) ... HeadObject ... Forbidden
```

> `s3:ListBucket`이 없어 S3는 404를 403으로 마스킹한다. 따라서 위 403이
> **"객체 없음"인지 "권한 없음"인지 현재로서는 구분할 수 없다.** 권한을 먼저 부여해야
> 객체 존재 여부를 확인할 수 있다.

### 필요한 정책 (최소)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOpenViduRecordings",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::projectree-bucket/meetings/*"
    }
  ]
}
```

`s3:GetObject`는 `HeadObject`와 `GetObject` 양쪽에 적용된다. Worker는 이 둘만 쓴다.
**쓰기 권한은 필요 없다** — Worker는 녹화 객체를 수정하거나 삭제하거나 복사하지 않는다.

### 선택 — 운영 진단용

```json
{
  "Sid": "DiagnoseOpenViduPrefix",
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": "arn:aws:s3:::projectree-bucket",
  "Condition": {
    "StringLike": { "s3:prefix": ["meetings/*"] }
  }
}
```

이것이 있어야 403과 404가 구분되어 장애 분석이 가능해진다.

### 기존 권한 유지

`audio-input/*`에 대한 기존 `s3:GetObject`는 **그대로 두어야 한다.**
S3 Event 기반 경로가 계속 동작해야 하기 때문이다.

---

## 2. SQS 권한

Worker가 사용하는 API는 다음 4개다.

```json
{
  "Sid": "ConsumeOpenViduQueue",
  "Effect": "Allow",
  "Action": [
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:ChangeMessageVisibility",
    "sqs:GetQueueAttributes"
  ],
  "Resource": "arn:aws:sqs:ap-northeast-2:<ACCOUNT_ID>:muOpenviduQueue"
}
```

| API | 사용처 |
|---|---|
| `ReceiveMessage` | long polling (`SqsAudioWorker.poll_once`) |
| `DeleteMessage` | **성공 시에만** 호출 |
| `ChangeMessageVisibility` | 처리 중 visibility heartbeat |
| `GetQueueAttributes` | 운영 점검 |

`sqs:SendMessage`는 **필요 없다.** Worker는 소비자 전용이다.

현재 이 4개는 이미 동작하는 것으로 실측 확인했다 (E2E 4회 성공).

---

## 3. DLQ 설정

### 현재 상태

```powershell
aws sqs get-queue-attributes --queue-url "<SQS_QUEUE_URL>" `
  --attribute-names RedrivePolicy
# → RedrivePolicy 없음
```

**DLQ가 없다.** 영구 실패 메시지가 무한 재시도된다. 실측 근거:

- 잘못된 key 테스트 메시지가 `ApproximateReceiveCount=23`까지 증가
- 기존 OpenVidu 메시지가 `41+`까지 증가

계약 전환기에는 실패가 늘어나므로 DLQ가 특히 중요하다.

### 권장 설정

```text
Main Queue : muOpenviduQueue
DLQ        : muOpenviduQueue-dlq
maxReceiveCount : 3 ~ 5
```

```json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-northeast-2:<ACCOUNT_ID>:muOpenviduQueue-dlq",
  "maxReceiveCount": "5"
}
```

`maxReceiveCount` 선택 근거:

- 현재 Worker 설정은 `SQS_VISIBILITY_TIMEOUT_SECONDS=900`, 최대 6회 heartbeat 연장.
- 일시적 실패(S3 5xx, Clova 타임아웃)는 3회 안에 대개 회복된다.
- 영구 실패(매핑 없음, IAM 거부, 손상 파일)는 재시도해도 회복되지 않으므로 빨리 격리하는 편이 낫다.
- **5**를 권장한다. 3은 긴 Clova 처리 중 visibility 만료가 겹치면 성급할 수 있다.

DLQ에도 Worker 역할의 `sqs:ReceiveMessage` / `sqs:DeleteMessage`를 부여하면 재처리 도구를 만들 수 있다.

---

## 4. 큐 공유 위험

### 확인된 사실

`muOpenviduQueue`에는 **OpenVidu egress 메시지만** 관측되었다 (4건, 전부 동일 구조).
이 큐에 다른 producer가 있다는 증거는 발견하지 못했다.

단, 이번 실험 과정에서 **우리가 직접 S3 Event 형식 메시지를 이 큐에 넣어** E2E를 검증했다.
즉 현재 이 큐는 사실상 두 계약을 함께 나르고 있으며, 새 라우터는 그 두 가지를 모두 처리한다.

### 확인이 필요한 사항

- Python Worker 외에 이 큐를 소비하는 컴포넌트가 있는가?
- 다른 소비자가 있다면 같은 메시지를 놓고 경합하게 된다.

**큐를 임의로 분리하거나 새로 생성하지 않았다.** 위험만 기록한다.

권장: 파이프라인 전용 큐를 두거나, 최소한 소비자가 Python Worker 하나임을 확인할 것.

---

## 5. 환경변수

Worker 호스트(EC2 등)에 설정한다.

```env
# --- 신규: OpenVidu egress 수집 ---
OPENVIDU_RECORDING_BUCKET=projectree-bucket
OPENVIDU_RECORDING_PREFIX=meetings/
OPENVIDU_SUPPORTED_KINDS=MIXED

# --- 기존 (그대로 사용) ---
AWS_REGION=ap-northeast-2
SQS_QUEUE_URL=<queue url>
S3_ALLOWED_BUCKETS=projectree-bucket
S3_INPUT_PREFIX=audio-input/test/
S3_ALLOWED_EXTENSIONS=.wav,.mp3,.m4a,.flac,.ogg,.aac
S3_MAX_AUDIO_BYTES=104857600
SQS_WAIT_TIME_SECONDS=20
SQS_VISIBILITY_TIMEOUT_SECONDS=900
SQS_HEARTBEAT_INTERVAL_SECONDS=300
SQS_HEARTBEAT_MAX_EXTENSIONS=6
UPLOAD_PROCESSING_TIMEOUT_SECONDS=1800
```

**`OPENVIDU_RECORDING_BUCKET`이 비어 있으면 OpenVidu 수집은 비활성**이며, Worker는
기존 S3 Event 경로만 처리한다. 즉 이 변경은 opt-in이고 배포해도 기존 동작을 바꾸지 않는다.

> `.env.example`은 사용자 미커밋 변경분이 있어 건드리지 않았다. 위 3개 신규 변수를
> `.env.example`에 추가하는 것을 권장한다.

---

## 6. AWS 콘솔 확인 절차

### 6-1. S3 권한 확인

1. IAM → 해당 사용자/역할 → 권한 정책에 `meetings/*` `s3:GetObject`가 있는지 확인
2. CLI로 검증:
   ```powershell
   aws s3api head-object --bucket projectree-bucket `
     --key "meetings/<roomName>/mixed/<timestamp>.ogg"
   ```
3. 성공 시 `ContentLength`, `ETag`, `ContentType`이 출력된다. 이 세 값이 Worker가 필요로 하는 값이다.

### 6-2. SQS 확인

1. SQS 콘솔 → `muOpenviduQueue` → 세부 정보
2. 확인 항목: `Messages available`, `Messages in flight`, `Visibility timeout`, `Dead-letter queue`
3. CLI:
   ```powershell
   aws sqs get-queue-attributes --queue-url "<SQS_QUEUE_URL>" `
     --attribute-names QueueArn VisibilityTimeout `
                       ApproximateNumberOfMessages `
                       ApproximateNumberOfMessagesNotVisible RedrivePolicy
   ```

### 6-3. DLQ 생성

1. SQS → 대기열 생성 → 이름 `muOpenviduQueue-dlq`, 표준 대기열
2. `muOpenviduQueue` → 편집 → 배달 못한 편지 대기열 → 활성화
3. DLQ ARN 선택, `maxReceiveCount = 5`
4. 저장 후 `RedrivePolicy`가 조회되는지 CLI로 재확인

### 6-4. 메시지 관찰 (삭제하지 않고)

```powershell
aws sqs receive-message --queue-url "<SQS_QUEUE_URL>" `
  --max-number-of-messages 10 --visibility-timeout 0 --wait-time-seconds 5
```

`--visibility-timeout 0`이면 즉시 큐로 되돌아간다. **운영 메시지를 삭제하지 말 것.**

---

## 7. EC2 IAM Role 적용 절차

장기적으로는 정적 액세스 키 대신 인스턴스 역할을 쓰는 것이 안전하다.

1. **역할 생성**
   IAM → 역할 → AWS 서비스 → EC2 →
   신뢰 정책 주체는 `ec2.amazonaws.com`

2. **정책 연결**
   §1(S3)과 §2(SQS)의 정책을 담은 고객 관리형 정책을 만들어 연결한다.
   `audio-input/*` 기존 권한도 함께 포함해야 한다.

3. **인스턴스에 연결**
   EC2 → 인스턴스 선택 → 작업 → 보안 → IAM 역할 수정 → 위 역할 선택
   (재시작 불필요, 수 초 내 반영)

4. **정적 키 제거**
   인스턴스의 `~/.aws/credentials`와 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
   환경변수를 제거한다. boto3는 자격증명 체인에서 인스턴스 메타데이터를 자동으로 찾는다.
   **코드 변경은 필요 없다** — `boto3.client("s3", region_name=...)`가 그대로 동작한다.

5. **검증**
   ```bash
   aws sts get-caller-identity      # Arn 이 .../assumed-role/... 로 바뀌어야 한다
   aws s3api head-object --bucket projectree-bucket --key "meetings/.../....ogg"
   ```

6. **주의**
   현재 로컬 개발 환경은 `AWS_PROFILE=dp-test` 프로필에 의존한다.
   기본 프로필에는 자격증명이 없어 이 변수 없이는 `NoCredentials`가 발생한다.
   EC2에서는 역할을 쓰므로 `AWS_PROFILE`을 설정하면 안 된다.

---

## 8. 적용 후 검증 체크리스트

```text
[ ] aws sts get-caller-identity 성공
[ ] meetings/* head-object 200 (403 아님)
[ ] SQS RedrivePolicy 조회됨
[ ] OPENVIDU_RECORDING_BUCKET 설정됨
[ ] MeetingContextResolver 운영 구현체 주입됨
[ ] Worker 기동 로그에 인증/권한 오류 없음
[ ] 신규 테스트 녹화 1건으로 E2E 성공
[ ] 성공 후 해당 메시지만 큐에서 사라짐
[ ] audio_upload_event 1행, request 1행 (중복 없음)
[ ] 동일 메시지 재전달 시 Clova/LLM 재호출 없음
```

---

## 9. 이번 작업에서 하지 않은 것

```text
IAM 정책 변경        : 하지 않음
DLQ 생성             : 하지 않음
큐 생성/분리         : 하지 않음
큐 purge             : 하지 않음
운영 메시지 삭제      : 하지 않음
S3 객체 생성/삭제/복사: 하지 않음
버킷 정책 변경        : 하지 않음
```

모두 문서화만 했다. 실제 적용은 인프라 담당자의 결정과 실행이 필요하다.
