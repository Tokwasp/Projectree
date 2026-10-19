# 🌳 Projectree — 화상 회의기반 노드 시각화 플랫폼

> 회의를 AI로 지식화하고, 프로젝트의 의사결정 흐름을 노드로 연결합니다.

"그래서 지난 회의에서 뭐 정했더라?" — 회의록 요약, 3D 노드 시각화, 개인 피드백까지 회의를 대신 정리해 주는 협업 서비스

---
## 💡 기획 배경

- 프로젝트를 진행하며 회의 내용이 Jira, Notion 등 여러 도구에 흩어져 **"그 작업 어디 있죠?", "전 회의에서 어떻게 하기로 했죠?"** 같은 질문이 반복됐습니다.
- 직장인은 근무 시간의 **20%** 를 정보 검색에 쓰고(McKinsey, 2012), 개발자의 **54%** 는 6개 이상의 도구를 사용합니다(Stack Overflow, 2025).
- 회의는 문제가 아니라 **기록이 이어져 있지 않은 것**이 문제였고, Projectree는 회의 내용을 자동으로 정리하고 결정 사항을 노드로 연결해 이를 해결합니다.

---
## 🚀 주요 기능

<table>
  <tr>
    <td align="center" width="50%">
      <b>팀원 초대</b><br><br>
      <img src="docs/images/feature-team-invite.png" width="400"><br>
      이메일로 여러 명의 팀원을 한 번에 초대
    </td>
    <td align="center" width="50%">
      <b>실시간 녹음 화상 회의</b><br><br>
      <img src="https://github.com/user-attachments/assets/2d795455-1bc2-414a-ad3f-30188f415345" width="400"><br>
      화상 회의를 진행하며 음성을 자동으로 녹음
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <b>회의 종료 후 산출물 선택</b><br><br>
      <img src="docs/images/feature-meeting-end.png" width="400"><br>
      회의 종료 시 노드, 회의록 요약 생성 여부 선택
    </td>
    <td align="center" width="50%">
      <b>회의록 요약</b><br><br>
      <img src="docs/images/feature-meeting-minutes.png" width="400"><br>
      회의 음성을 텍스트로 변환<br>핵심 내용을 자동으로 요약
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <b>3D 노드 시각화</b><br><br>
      <img src="https://github.com/user-attachments/assets/a7dfdc0f-ce34-4039-813b-bc7a117c012b" width="400"><br>
      회의 내용을 노드로 3D 시각화<br>프로젝트 흐름을 한눈에 확인
    </td>
    <td align="center" width="50%">
      <b>AI 개인 피드백</b><br><br>
      <img src="docs/images/feature-personal-feedback.png" width="400"><br>
      참석자마다 말하기 습관 피드백 제공<br>팀원별 발화 비율 확인
    </td>
  </tr>
</table>

---
## 🛠️ 기술 스택

### Frontend
- React, TypeScript, Vite
- Zustand, React Router
- three.js, React Three Fiber (3D 노드 그래프)

### Backend
- Java 21, Spring Boot, Spring Data JPA, QueryDSL
- Python, FastAPI, SQLAlchemy
- MySQL, PostgreSQL(pgvector), Redis
- Naver Clova Speech(STT), LLM(GMS), ffmpeg

### Infra
- AWS ECS Fargate, EC2, RDS, S3, SQS, ALB, Route 53, VPC
- OpenVidu (화상 회의 서버)
- Upstash Redis, Jenkins, Vercel

---
## 🏗️ 시스템 아키텍처

<img width="3963" height="2436" alt="Projectree" src="https://github.com/user-attachments/assets/80f1d5c1-5ee0-4c25-8171-89254aa668e7" />

1. **화상 회의** — OpenVidu 3를 별도 EC2로 분리해 WebRTC 화상 회의/녹음을 처리
2. **파이프라인** — 녹음 오디오를 Mixed-Audio Queue / Personal-Audio Queue(SQS) 두 개로 나눠 비동기 처리
   - Mixed-Audio Queue → EC2 FastAPI Worker → Naver Clova STT → LLM 분석 → 회의록·노드 그래프 생성
   - Personal-Audio Queue → EC2 Spring AI Worker → OpenAI 호환 API → 개인별 피드백 생성

---
### 커밋 메시지 타입 프리픽스                                                                                                                                                                                                                                                                                                                                         
| 타입 | 용도 |                                                                                                                                                       
| --- | --- |                                                                                                                                                         
| `feat:` | 새 기능 추가 |                                                                                                                                            
| `fix:` | 버그 수정 |                                                                                                                                                
| `test:` | 테스트 추가/수정 |                                                                                                                                        
| `chore:` | 빌드, 설정 등 잡무성 변경 |                                                                                                                              
| `refactor:` | 동작 변경 없는 리팩터링 |                                                                                                                             
| `style:` | 포맷팅, 세미콜론 등 코드 스타일 |                                                                                                                        
| `docs:` | 문서 변경 |                                                                                                                                               
| `ci:` | CI/CD 설정 변경 |
---
## Jira 활용 방식

### 이슈 계층 구조
`에픽(Epic) → 스토리(Story) → 하위 작업(Sub-task)` 3단계로 업무를 분해해 관리

- **에픽**: 기능 단위의 큰 묶음 (예: `사용자 인증`)
- **스토리**: 사용자 관점의 기능 (예: `소셜 로그인`, `로그아웃`, `회원 탈퇴`, `프로필 조회`)
- **하위 작업**: 실제 구현 단위 작업 (예: `[BE] 회원 탈퇴 API 만들기`)
<img width="1414" height="556" alt="image" src="https://github.com/user-attachments/assets/6a3eb968-3730-49de-b332-08e4f8eca372" />

---
## 📦 폴더 구조

```text
S15P11D205/
├─ Backend/                 # API 서버
│  └─ src/main/java/com/ssafy/projectree/domain/
│     ├─ member/ project/ meeting/ meetingreview/ nodeCategory/ notification/ mail/ uploadfile/
├─ Frontend/                # 웹 화면
│  └─ src/page/
├─ data-pipeline/           # 회의 분석·노드 생성
│  └─ data_pipeline/
├─ personal-audio-backend/  # 개인 피드백 서버
│  └─ src/main/java/ssafy/personal_audio_backend/domain/review/
└─ exec/                    # 포팅 매뉴얼
```

## 📄 문서 / 트러블슈팅

- [SQS 도입으로 회의 분석 요청 유실 방지](docs/troubleshooting/messaging-queue.md)

## 👥 팀 소개

| 이름 | 역할 |
| --- | --- |
| 조희제 | Backend, Infra |
| 김경현 | Backend |
| 안현석 | FrontEnd, BackEnd |
| 이상민 | Infra |
| 이종원 | AI |
| 정서영 | FrontEnd |
