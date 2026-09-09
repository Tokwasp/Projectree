# SSE 실시간 알림 유실 대응
 
> 화상 회의 분석 완료 알림이 사용자에게 도달하지 않는 문제를, 커넥션 유지 · 인스턴스 간 전파 · 유실 복구 3계층으로 해결한 과정
 
---
 
## 1. 문제 상황
 
화상 회의 종료 후 노드/회의록 생성을 신청하면, 작업이 완료될 때 실시간 알림을 받아야 합니다.
그런데 **작업은 정상적으로 완료되었는데 알림만 오지 않는 경우**가 발생했습니다.
 
- DB에는 노드와 회의록이 정상 생성되어 있음
- 사용자는 아무 알림도 받지 못해, 새로고침 전까지 완료 사실을 알 수 없음
- 항상 재현되지 않고 특정 상황에서만 발생
즉 **작업 처리는 성공했지만 전달 계층에서 유실**되는 문제였습니다.
 
---
 
## 2. 관련 비즈니스 로직
 
| 요구사항 | 설명 |
| --- | --- |
| 노드 / 회의록 생성 | 회원은 화상 회의 종료 후 노드와 회의록 생성을 체크할 수 있다 |
| 실시간 알림 | 노드 혹은 회의록 생성이 완료되면 실시간 알림을 받는다 |
 
분석 작업은 STT와 LLM 호출을 포함해 **수십 초에서 수 분**이 걸립니다.
사용자는 그동안 화면을 켜둔 채 대기하므로, **알림 유실은 곧 "작업이 끝났는지 알 수 없는 상태"**가 됩니다.
 
---
 
## 3. 기존 구조
 
작업 요청은 SQS를 통해 Python 분석 모듈로 전달되고, 처리 결과는 **Spring 서버로 콜백**됩니다.
Spring 서버는 결과를 받아 알림을 생성하고, **SSE(Server-Sent Events)** 로 클라이언트에 전달했습니다.
 
```
[Client] --SSE 구독--> [Spring Server]
                            ↑
                        콜백(작업 완료)
                            │
[SQS] → [Python 분석 모듈] ──┘
```
 
### 커넥션은 회원 ID 기준으로 보관한다
 
```java
private final Map<Integer, List<SseEmitter>> emitters = new ConcurrentHashMap<>();
```
 
`SseEmitter`는 살아있는 HTTP 응답 스트림을 쥐고 있어 직렬화할 수 없습니다.
따라서 외부 저장소에 둘 수 없고, **각 서버 인스턴스의 로컬 메모리**에만 존재합니다.
 
키를 작업 단위(commandId)가 아니라 **회원 ID**로 잡은 이유는 커넥션과 작업의 생명주기가 다르기 때문입니다.
 
```
페이지 진입     → SSE 구독 (아직 아무 작업 요청도 없음)
회의 종료       → 노드 생성 요청 / 회의록 생성 요청
다른 경로       → 프로젝트 초대 알림 (분석과 무관)
                      ↑ 이 모두가 하나의 SSE 연결을 공유
```
 
연결이 작업보다 먼저 열리고, 여러 작업과 분석 외 알림이 같은 연결을 사용합니다.
값이 `List`인 것도 같은 이유로, **한 회원이 여러 탭·기기에서 동시에 접속**할 수 있어 모든 커넥션에 전송해야 합니다.
 
### 문제 지점
 
콜백이 도착한 시점에 **보낼 대상 `SseEmitter`가 없으면 알림은 그대로 폐기**됩니다.
로그를 보면 알림 엔티티는 생성되었는데 전송 로그가 남지 않는 케이스가 존재했고, 원인은 하나가 아니었습니다.
 
---
 
## 4. 원인 분석
 
### 4-1. ALB idle timeout에 의한 커넥션 절단
 
AWS ALB의 기본 idle timeout은 **60초**입니다.
SSE는 연결만 열어두고 이벤트가 없으면 아무 데이터도 흐르지 않기 때문에, **60초 동안 전송이 없으면 ALB가 커넥션을 끊습니다.**
 
분석 작업은 60초를 넘기는 경우가 많아 다음 흐름이 발생했습니다.
 
```
60초 무전송 → ALB 커넥션 종료 → 서버 emitter 무효화
→ 그 사이 작업 완료 콜백 도착 → 보낼 emitter 없음 → 알림 폐기
→ 브라우저는 자동 재연결에 성공하지만, 이미 지나간 알림은 받지 못함
```
 
브라우저 `EventSource`는 끊기면 자동으로 재연결하기 때문에 **클라이언트 입장에서는 연결이 정상으로 보이고**, 그래서 원인 파악이 늦어졌습니다.
 
### 4-2. 죽은 커넥션의 누적
 
ALB가 커넥션을 닫아도 **서버는 다음 쓰기를 시도하기 전까지 그 사실을 알 수 없습니다.**
그런데 ALB가 끊는 조건이 바로 "아무것도 보내지 않은 상태"이므로, 실패를 감지할 계기 자체가 없었습니다.
 
```
t=0     구독            → List = [#1]
t=0~60  알림 없음 (write 없음 → 커넥션 상태 확인 불가)
t=60    ALB 절단 (서버는 모름)
t=63    브라우저 자동 재연결 → List = [#1(죽음), #2]
t=123   절단 → 재연결        → List = [#1, #2(죽음), #3]
...
30분 후  SseEmitter 타임아웃 → 그제서야 onTimeout으로 제거
```
 
키가 회원 ID이므로 재연결할 때마다 같은 리스트에 계속 추가되고, 죽은 emitter가 60초마다 하나씩 쌓입니다.
GC도 이를 회수하지 못합니다. 맵이 강한 참조로 붙잡고 있어 **참조는 유효하지만 쓸모는 없는 상태**이기 때문입니다.
emitter 하나는 완료되지 않은 서블릿 비동기 요청 컨텍스트와 그에 딸린 자원을 함께 물고 있습니다.
 
다음 알림이 전송될 때 실패를 감지해 정리되기는 하지만, **이 서비스는 알림이 드물게 오는 패턴**입니다.
쌓이는 속도(60초당 1개)가 청소 계기(알림 발생)보다 훨씬 빠릅니다.
 
### 4-3. 다중 인스턴스 환경에서의 전달 실패
 
Spring 서버는 **ECS Fargate에 다중 태스크**로 운영됩니다.
emitter가 각 태스크의 로컬 메모리에만 있으므로 다음 문제가 생깁니다.
 
```
사용자가 SSE 연결 → A 태스크에 emitter 저장
작업 완료 콜백    → ALB가 B 태스크로 라우팅
B 태스크에는 emitter 없음 → 알림 폐기
```
 
**타임아웃과 무관하게, 연결된 태스크와 콜백을 받은 태스크가 다르면 무조건 유실**되는 구조였습니다.
 
### 4-4. 끊긴 구간의 알림 복구 수단 부재
 
위 문제를 모두 해결하더라도, 배포·스케일 인·모바일 네트워크 전환으로 커넥션이 끊기는 순간은 반드시 존재합니다.
재연결에 성공해도 **끊겨 있던 동안 발생한 알림을 되찾을 방법이 없었습니다.**
 
---
 
## 5. 해결 과정
 
> 브라우저 자동 재연결은 **연결을 복구할 뿐 그 사이의 알림을 복구하지 못하고**, 서버에는 죽은 emitter가 누적된다.
> 그래서 하트비트로 끊김 자체를 줄이면서 죽은 커넥션을 감지하고, 그럼에도 끊기는 구간은 Last-Event-ID 재전송으로 메운다.
 
### 5-1. 하트비트로 커넥션 유지 (ALB timeout 대응)
 
#### 왜 브라우저 자동 재연결에 맡기지 않았는가
 
`EventSource`는 끊기면 알아서 재연결하므로, 언뜻 별도 대응이 불필요해 보입니다. 그러나
 
- 재연결에는 수 초의 공백이 있고, **그 사이 도착한 알림은 폐기**됩니다
- 60초마다 절단이 반복되므로 그 공백도 반복됩니다
- 4-2처럼 죽은 emitter가 계속 누적됩니다
- 재연결 요청은 매번 TLS 핸드셰이크·인증·재전송 조회를 새로 수행합니다
무엇보다, 재연결의 안전망이 되어야 할 `Last-Event-ID`가 **첫 절단에서는 동작하지 않습니다.**
브라우저는 `id` 필드가 붙은 이벤트를 실제로 받은 적이 있어야 이 헤더를 보내는데, 구독 직후의 connect 이벤트에는 `id`가 없기 때문입니다.
 
```
구독 → connect 수신(id 없음) → 60초 무전송 → 절단
→ 재연결 (Last-Event-ID 헤더 없음) → 재전송 스킵 → 알림 영구 유실
```
 
즉 "분석을 걸어두고 첫 알림을 기다리는" 바로 그 상황에서 안전망이 비어 있었습니다.
 
#### 기술 선정
 
| 후보 | 장점 | 채택하지 않은 이유 |
| --- | --- | --- |
| 자동 재연결에 위임 | 추가 구현 없음 | 재연결 공백의 알림 유실, emitter 누적, 첫 절단에서 재전송 불가 |
| ALB idle timeout 상향 | 설정 한 줄로 해결 | 중간 프록시·모바일 네트워크 절단은 못 막고, **죽은 커넥션 감지 수단이 없음** |
| **주기적 하트비트** ✅ | 커넥션 유지 + 죽은 커넥션 감지 | — |
 
인프라 설정에 의존하기보다, **애플리케이션이 스스로 커넥션 상태를 확인**할 수 있는 하트비트를 선택했습니다.
 
#### 구현
 
ALB timeout의 절반인 **30초** 주기로 모든 emitter에 keep-alive를 전송합니다.
 
```java
@Scheduled(fixedRateString = "${app.notification.sse.heartbeat-interval}")
public void sendHeartbeat() {
    emitterRepository.findAll().forEach((memberId, emitters) ->
            emitters.forEach(emitter -> notificationSender.sendHeartbeat(memberId, emitter)));
}
```
 
이때 **더미 데이터가 아니라 SSE 주석(comment)** 을 보냅니다.
 
```java
public void sendHeartbeat(int memberId, SseEmitter emitter) {
    try {
        emitter.send(SseEmitter.event().comment("keep-alive"));
    } catch (IOException | IllegalStateException e) {
        log.debug("SSE 하트비트 체크 실패 memberId={}", memberId);
        completeAndRemove(memberId, emitter);   // 죽은 커넥션 정리
    }
}
```
 
주석 이벤트를 선택한 이유는 두 가지입니다.
 
- 클라이언트의 `onmessage` 핸들러를 깨우지 않아, **프론트에서 더미 데이터를 걸러낼 필요가 없음**
- `id` 필드가 없으므로 **브라우저가 보관하는 `Last-Event-ID`를 오염시키지 않음** (5-3의 전제)
정리는 참조 제거와 비동기 요청 종료를 함께 수행해야 합니다.
 
```java
public void completeAndRemove(int memberId, SseEmitter emitter) {
    emitterRepository.delete(memberId, emitter);  // 맵에서 참조 제거 → GC 대상이 됨
    try {
        emitter.complete();                       // 비동기 요청 종료 → 컨테이너 자원 반납
    } catch (Exception e) {
        log.debug("이미 끊긴 emitter 정리 중 예외 무시 memberId={}", memberId);
    }
}
```
 
결과적으로 하트비트는 두 가지 역할을 합니다.
 
| | 하트비트 없음 | 하트비트 있음 |
| --- | --- | --- |
| 절단 자체 | 60초마다 반복 발생 | **무전송 상태가 없어져 발생하지 않음** |
| 죽은 커넥션 정리 | 다음 알림 발생 시 (수 시간 뒤일 수도) | 최대 30초 |
 
```yaml
app:
  notification:
    sse:
      # 세션 타임아웃과 맞춘다. 브라우저가 자동 재연결하므로 죽은 연결을 청소하는 주기에 가깝다.
      timeout: 30m
      # ALB idle timeout(60초)의 절반.
      heartbeat-interval: 30s
```
 
`SseEmitter` 타임아웃도 기본값에 맡기지 않고 30분으로 명시했습니다.
타임아웃은 ALB에만 있는 것이 아니라 **애플리케이션(Spring MVC async) 계층에도 존재**하기 때문에, 한쪽만 해결하면 증상이 재현될 수 있습니다.
 
### 5-2. Redis Pub/Sub로 인스턴스 간 전파
 
emitter는 직렬화할 수 없어 공유 저장소에 둘 수 없습니다.
그래서 **emitter를 공유하는 대신, 알림 이벤트를 모든 인스턴스에 방송**하는 방향을 택했습니다.
 
```java
// 발행: 콜백을 받은 태스크
public void publish(NotificationMessage message) {
    stringRedisTemplate.convertAndSend(
            NotificationConfig.NOTIFICATION_TOPIC,
            objectMapper.writeValueAsString(message)
    );
}
 
// 구독: 모든 태스크
@Override
public void onMessage(Message message, byte[] pattern) {
    NotificationMessage payload = objectMapper.readValue(...);
 
    emitterRepository.findAllByMemberId(payload.getReceiverId())
            .forEach(emitter -> notificationSender.send(
                    payload.getReceiverId(),
                    emitter,
                    String.valueOf(payload.getNotificationId()),
                    NOTIFICATION_EVENT,
                    payload));
}
```
 
어느 태스크가 콜백을 받든 모든 태스크가 이벤트를 수신하고, **실제 커넥션을 가진 태스크만 전송**합니다.
Redis는 커넥션 저장소가 아니라 **브로커 역할**만 담당합니다. 이미 인프라에 있어 추가 운영 부담 없이 적용할 수 있었습니다.
 
다만 **Redis Pub/Sub는 전달을 보장하지 않습니다.** 구독자가 순간적으로 끊겨 있으면 그 메시지는 사라집니다.
이 빈틈은 다음 5-3에서 메웁니다.
 
### 5-3. Last-Event-ID로 유실 알림 복구
 
알림은 발행 전에 **DB에 먼저 저장**하고, 그 PK를 SSE 이벤트 ID로 사용합니다.
 
```java
Notification notification = notificationRepository.save(Notification.of(type, receiverId));
notificationPublisher.publish(NotificationMessage.from(notification));
```
 
```java
emitter.send(SseEmitter.event()
        .id(eventId)          // = notification.id
        .name(NOTIFICATION_EVENT)
        .data(data, MediaType.APPLICATION_JSON));
```
 
`id` 필드를 붙여야 브라우저가 마지막 수신 ID를 기억하고, **재연결 시 `Last-Event-ID` 헤더를 자동으로 전송**합니다.
서버는 이 값보다 큰 ID의 알림을 조회해 재전송합니다.
 
```java
@Query("""
        select n from Notification n
        where n.receiverId = :memberId
          and n.id > :lastEventId
        order by n.id asc
        """)
List<Notification> findNotReceivedMessages(int memberId, int lastEventId);
```
 
```java
public SseEmitter subscribe(int memberId, Integer lastEventId) {
    SseEmitter emitter = emitterRepository.save(memberId, createEmitter());
 
    emitter.onCompletion(() -> emitterRepository.delete(memberId, emitter));
    emitter.onTimeout(() -> notificationSender.completeAndRemove(memberId, emitter));
    emitter.onError(throwable -> notificationSender.completeAndRemove(memberId, emitter));
 
    notificationSender.sendSubscriptionMessage(memberId, emitter, "connect", "연결되었습니다.");
 
    if (isValidLastEventId(lastEventId)) {
        notificationRepository.findNotReceivedMessages(memberId, lastEventId)
                .forEach(notification -> notificationSender.send(...));
    }
    return emitter;
}
```
 
여기서 중요한 점은 **`Last-Event-ID`는 헤더만 받는다고 동작하지 않는다는 것**입니다.
 
- 서버가 이벤트에 `id`를 붙여야 브라우저가 헤더를 보내고
- 지난 알림이 **애플리케이션 외부(DB)에 영속**되어 있어야 재전송이 가능합니다
알림을 메모리에만 보관했다면, 이전 [메시징 큐 도입](./messaging-queue.md) 문서에서 겪은 "애플리케이션 메모리에 있는 것은 유실된다"는 문제를 그대로 반복하게 됩니다.
 
### 5-4. 중복 전달 방지
 
재전송을 도입하면 필연적으로 중복 문제가 따라옵니다. 식별자를 계층별로 나눠 처리했습니다.
 
| 식별자 | 위치 | 막는 중복 |
| --- | --- | --- |
| `eventId` (UUID) | `meeting_analysis_result_inbox` 유니크 제약 | SQS at-least-once로 같은 결과 이벤트가 두 번 도착 |
| `commandId + audience + notificationType` | `meeting_analysis_notification_outbox` 유니크 제약 | 같은 작업에 같은 종류 알림이 두 번 생성 |
| `notification.id` | SSE `id` 필드 | 재연결 시 실시간 + 재전송으로 두 번 도달 (클라이언트 멱등 처리) |
 
노드 생성과 회의록 생성이 서로 충돌하지 않는 것은 **유니크 키에 알림 타입이 포함**되어 있기 때문입니다.
 
```java
@UniqueConstraint(
    name = "uk_meeting_analysis_notification_command_audience_type",
    columnNames = {"command_id", "audience", "notification_type"}
)
```
 
```
MEETING_SUMMARY_ANALYSIS_SUCCEEDED (회의록) → 1건 허용
MEETING_NODE_ANALYSIS_SUCCEEDED    (노드)   → 1건 허용
```
 
타입이 다르면 별개의 행이 되어 각각 발행되고, **같은 타입이 다시 들어올 때만** 차단됩니다.
 
다만 유니크 제약은 최후의 방어선이고, 1차 방어는 도메인 상태 전이입니다.
 
```java
AnalysisTaskCompletionResult completion = completeSummary(meeting);
 
if (completion == AnalysisTaskCompletionResult.APPLIED) {
    notificationOutboxRepository.saveAndFlush(createNotification(...));
}
```
 
상태가 실제로 변경되었을 때만 알림을 생성하고, 회의 조회에 비관적 락(`findByIdForUpdate`)을 걸어
여러 태스크가 같은 이벤트를 동시에 처리해도 한쪽만 통과하도록 했습니다.
 
---
 
## 6. 개선 결과
 
```
[SQS] → [Python 분석 모듈] ──콜백──> [Spring Server (태스크 N개)]
                                          │
                                  ① Notification DB 저장 (id = 이벤트 순번)
                                          │
                                  ② Redis Pub/Sub 발행
                                          ↓
                              모든 태스크 Subscriber 수신
                                          ↓
                              커넥션 보유 태스크만 SSE 전송
                                          ↓
                                      [Client]
                                          │
                              (끊김 발생 시 자동 재연결)
                                          ↓
                              Last-Event-ID 헤더 → id 이후 알림 재전송
```
 
각 계층이 서로 다른 실패 지점을 담당합니다.
 
| 계층 | 대응 | 막는 문제 |
| --- | --- | --- |
| 커넥션 유지 | 30초 하트비트 (ALB 60초의 절반) | idle timeout 절단, 죽은 emitter 누적 |
| 인스턴스 간 전파 | Redis Pub/Sub 브로드캐스트 | 다른 태스크가 콜백을 받았을 때의 유실 |
| 유실 복구 | DB 저장 + Last-Event-ID 재전송 | 끊긴 구간의 알림, Pub/Sub의 미보장 특성 |
| 중복 방지 | Inbox·Outbox 유니크 제약 + 상태 전이 | 재처리·재전송으로 인한 중복 알림 |
 
- 60초를 넘기는 분석 작업에서도 커넥션이 유지되어 알림이 즉시 전달됨
- 죽은 emitter가 최대 30초 안에 정리되어, 30분간 누적되던 비동기 요청 자원 낭비 제거
- 태스크 수를 늘려도 알림 전달이 깨지지 않아 **수평 확장이 가능한 구조**가 됨
- 배포·네트워크 절단으로 끊겨도 재연결 시점에 누락분을 이어서 수신

