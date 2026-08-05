# Meeting Analysis Command Join v1

## 두 입력

OpenVidu Recording Ready Queue는 `projectId`, UUID `roomName`, `kind=MIXED`, `objectKey`, `egressId`, `memberId`, `endedAt`을 전달한다. Java Command Queue는 `commandSchemaVersion=1`, UUID `commandId`, `commandType=MEETING_ANALYSIS_REQUESTED`, UTC `requestedAt`, 양의 64-bit 정수 `projectId`, 그리고 `meetingId`, 같은 UUID `roomName`, 두 boolean 옵션을 전달한다.

Join key는 `(projectId, roomName)`이다. Recording message에는 meetingId/commandId가 없으므로 추측하지 않는다.

## 소비와 순서 역전

각 consumer는 엄격히 검증한 입력을 DB에 commit한 뒤 즉시 SQS ACK한다. STT/LLM은 SQS consumer에서 실행하지 않는다.

- Recording 먼저: `WAITING_FOR_COMMAND`
- Command 먼저: `WAITING_FOR_RECORDING`
- 둘이 일치: command/recording/task를 `READY`

동일 식별자와 같은 payload는 no-op이다. 같은 식별자에 다른 payload는 명시적 conflict이며 ACK하지 않는다. Command는 `(project_id, meeting_id)`당 하나다. 입력 대기 timeout은 두지 않는다.

Coordinator가 READY task를 DB에서 claim한 후 S3 Head/Get, 기존 audio identity claim, STT 저장을 수행한다. SUMMARY/NODES가 모두 선택되어도 Transcript는 한 번 생성해 공유한다. 오래된 claim은 timeout 후 회수할 수 있다.

## 프로세스

```powershell
python -m data_pipeline.meeting_analysis recording-ready-consumer
python -m data_pipeline.meeting_analysis analysis-command-consumer
python -m data_pipeline.meeting_analysis coordinator
python -m data_pipeline.outbox_publisher
```

기존 장시간 `SqsAudioWorker`의 OpenVidu 호환 경로는 `ENABLE_LEGACY_OPENVIDU_AUDIO_WORKER=true`가 아니면 비활성이다.
