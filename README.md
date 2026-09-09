# 🌳 Projectree — 화상 회의기반 노드 시각화 플랫폼

> 회의를 AI로 지식화하고, 프로젝트의 의사결정 흐름을 노드로 연결합니다.

화상 회의 음성을 AI를 통해 회의록을 만들고, 결정·작업·이슈를 **3D 그래프**로 시각화하여 프로젝트 관리하는 서비스

<img width="1920" height="975" alt="image" src="https://github.com/user-attachments/assets/2d795455-1bc2-414a-ad3f-30188f415345" />
<img width="2879" height="1456" alt="image" src="https://github.com/user-attachments/assets/a7dfdc0f-ce34-4039-813b-bc7a117c012b" />


---
## 🚀 주요 기능

- **실시간 녹음 화상 회의** — OpenVidu 기반 화상 회의를 진행하며 음성을 녹음합니다.
- **회의 분석 기반 회의록 생성** — 녹음된 음성을 STT로 텍스트화하고 LLM으로 요약해 회의 요약을 자동 생성합니다.
- **회의 분석 기반 프로젝트 시각화** — 회의에서 추출한 결정/작업/이슈를 노드로 만들어 three.js 기반 3D 그래프로 시각화합니다.
- **개인별 회의 피드백** — 화자 분리를 통해 참석자별 발화를 분석하고 개인별 피드백을 제공합니다.

---
## 🛠️ 기술 스택
### Frontend (`Frontend/`)
- React 19 + TypeScript, Vite 8
- React Router DOM, Zustand (상태 관리)
- three.js / React Three Fiber / drei — 3D 노드 그래프 렌더링

### Backend (`Backend/`)
- Java 21, Spring Boot 4.1.0 (Spring MVC, Spring Data JPA, QueryDSL)
- MySQL 8.0, Redis
- AWS SDK(SQS, S3)
- 배포: AWS ECS Fargate

### data-pipeline (`data-pipeline/`)
- Python 3.11, FastAPI + Uvicorn
- SQLAlchemy + Alembic, PostgreSQL(pgvector)
- Naver Clova Speech(STT), OpenAI 호환 GMS Client(LLM)

### personal-audio-backend (`personal-audio-backend/`)
- Java 21, Spring Boot 4.1.0
- MySQL, AWS SQS/S3, ffmpeg(음성 처리)
- OpenAI 호환 GMS Client — 개인별 회의 피드백 생성
- 배포: EC2

### Infra / CI-CD
- AWS: Route 53, ALB, VPC, ECS Fargate, EC2, RDS, S3, SQS
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
├─ Backend/                 # Spring Boot API 서버 (회원/프로젝트/회의/노드 도메인)
│  └─ src/main/java/com/ssafy/projectree/domain/
│     ├─ member/ project/ meeting/ meetingreview/ nodeCategory/ notification/ mail/ uploadfile/
├─ Frontend/                # React + Vite SPA
│  └─ src/page/             # Auth/ Home/ Landing/ MyPage/ Project(Create/Home/Meeting/Tree/Member/...)
├─ data-pipeline/            # Python FastAPI 기반 회의 분석·노드 생성 파이프라인
│  └─ data_pipeline/         # api/ meeting_analysis/ stt/ llm/ storage/ worker/ outbox_publisher/ ...
├─ personal-audio-backend/  # 개인별 회의 피드백 생성 Spring Boot 서버
│  └─ src/main/java/ssafy/personal_audio_backend/domain/review/
└─ exec/                     # 포팅 매뉴얼 등 실행/배포 산출물
```

## 📄 문서 / 트러블슈팅

- [메시징 큐 적용](docs/troubleshooting/messaging-queue.md)

## 👥 팀 소개

| 이름 | 역할 |
| --- | --- |
| 조희제 | Backend, Infra |
| 김경현 | Backend |
| 안현석 | FrontEnd, BackEnd |
| 이상민 | Infra |
| 이종원 | AI |
| 정서영 | FrontEnd |
