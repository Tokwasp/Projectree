# Meeting Redis Smoke Test

`MeetingRedisSmokeTest`는 운영 코드와 동일한 `StringRedisTemplate`,
`MeetingRoomRedisReader`, `MeetingSynchronizationService`를 사용해 스테이징 또는 개발용
Upstash Redis의 SCAN/HASH/TTL 계약을 확인한다.

기본 `test` 작업에서는 `smoke` 태그가 제외된다. Smoke Test가 만드는 정상 HASH Key와
WRONGTYPE STRING Key에는 60초 TTL이 설정되며 테스트에서 직접 삭제하지 않는다. 다른
Redis Key는 수정하거나 삭제하지 않는다.

## 실행 전 안전 확인

- 대상 Redis가 반드시 staging/dev인지 확인한다.
- production Redis 또는 production Spring profile에서는 실행하지 않는다.
- 실제 접속 정보와 비밀번호를 코드, 로그, 작업 결과에 남기지 않는다.
- 두 쓰기 허용 환경변수가 모두 `true`일 때만 실행된다.

## PowerShell 실행

```powershell
$env:MEETING_REDIS_SMOKE_ENABLED="true"
$env:MEETING_REDIS_SMOKE_ALLOW_WRITE="true"

$env:REDIS_HOST="<staging-upstash-host>"
$env:REDIS_PORT="<staging-upstash-port>"
$env:REDIS_PASSWORD="<staging-upstash-password>"

.\gradlew.bat smokeTest
```

SSL/TLS는 애플리케이션의 기존 Upstash 설정과 동일하게 활성화된다. 환경변수가 없거나
두 쓰기 허용 플래그 중 하나라도 `true`가 아니면 Smoke Test는 실패하지 않고 SKIP된다.

## 운영 MySQL UNIQUE 배포 확인

배포 전에 실제 테이블 정의를 확인한다.

```sql
SHOW CREATE TABLE meeting;
```

`uk_meeting_room_name` UNIQUE 제약이 없다면 먼저 중복 데이터를 확인한다.

```sql
SELECT room_name, COUNT(*)
FROM meeting
GROUP BY room_name
HAVING COUNT(*) > 1;
```

중복이 없고 별도 Migration에서 관리하지 않는 경우에만 제약을 적용한다.

```sql
ALTER TABLE meeting
ADD CONSTRAINT uk_meeting_room_name
UNIQUE (room_name);
```

현재 프로젝트는 `ddl-auto=update`를 사용하므로 배포 환경의 실제 제약 존재 여부를 별도로
검증해야 한다.
