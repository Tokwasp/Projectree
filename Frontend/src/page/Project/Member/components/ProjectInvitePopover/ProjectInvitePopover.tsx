import {
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type {
  InviteResult,
  MemberSearchResponse,
} from "../../api/projectInvitationApi";
import useProjectInvitation from "../../hooks/useProjectInvitation";
import { toast } from "../../../../../store/toastStore";
import style from "./ProjectInvitePopover.module.css";

interface ProjectInvitePopoverProps {
  projectId: number | null;
  existingMemberIds: number[];
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_INVITE_COUNT = 10;

function getInviteResultMessage(result: InviteResult) {
  switch (result) {
    case "MEMBER_NOT_FOUND":
      return "존재하지 않는 회원입니다.";
    case "ALREADY_MEMBER":
      return "이미 프로젝트에 참여 중인 회원입니다.";
    case "SELF_INVITE":
      return "자기 자신은 초대할 수 없습니다.";
    case "COOLDOWN":
      return "잠시 후 다시 초대해주세요.";
    default:
      return "팀원 초대에 실패했습니다.";
  }
}

export default function ProjectInvitePopover({
  projectId,
  existingMemberIds,
}: ProjectInvitePopoverProps) {
  const {
    searchMember,
    inviteMembers,
    isSearching,
    isInviting,
    error: invitationError,
    clearError: clearInvitationError,
  } = useProjectInvitation();

  const [isOpen, setIsOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [selectedMembers, setSelectedMembers] = useState<
    MemberSearchResponse[]
  >([]);
  const [errorMessage, setErrorMessage] = useState("");

  const trimmedEmail = email.trim().toLowerCase();

  const close = () => {
    setIsOpen(false);
    setEmail("");
    setSelectedMembers([]);
    setErrorMessage("");
    clearInvitationError();
  };

  const handleEmailAdd = async () => {
    if (!trimmedEmail) {
      return;
    }

    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setErrorMessage("올바른 이메일 주소를 입력해주세요.");
      return;
    }

    if (
      selectedMembers.some(
        (member) => member.email.toLowerCase() === trimmedEmail,
      )
    ) {
      setErrorMessage("이미 추가한 이메일입니다.");
      return;
    }

    if (selectedMembers.length >= MAX_INVITE_COUNT) {
      setErrorMessage(
        `한 번에 최대 ${MAX_INVITE_COUNT}명까지 초대할 수 있습니다.`,
      );
      return;
    }

    const foundMember = await searchMember(trimmedEmail);

    if (!foundMember) {
      return;
    }

    if (existingMemberIds.includes(foundMember.memberId)) {
      setErrorMessage("이미 프로젝트에 참여 중인 회원입니다.");
      return;
    }

    setSelectedMembers((currentMembers) => [
      ...currentMembers,
      foundMember,
    ]);
    setEmail("");
    setErrorMessage("");
  };

  const handleMemberRemove = (memberId: number) => {
    setSelectedMembers((currentMembers) =>
      currentMembers.filter(
        (selectedMember) => selectedMember.memberId !== memberId,
      ),
    );
    setErrorMessage("");
    clearInvitationError();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      void handleEmailAdd();
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (projectId === null || selectedMembers.length === 0) {
      return;
    }

    const response = await inviteMembers(
      projectId,
      selectedMembers.map((member) => member.memberId),
    );

    if (!response) {
      return;
    }

    const failedResults = response.results.filter(
      ({ result }) => result !== "INVITED" && result !== "RESENT",
    );

    if (failedResults.length === 0) {
      // 팝오버가 닫히면서 결과가 같이 사라진다 — 몇 명에게 갔는지는 토스트로 남긴다
      toast.success(`${selectedMembers.length}명에게 초대를 보냈습니다.`);
      close();
      return;
    }

    const failedMemberIds = new Set(
      failedResults.map(({ inviteeMemberId }) => inviteeMemberId),
    );

    setSelectedMembers((currentMembers) =>
      currentMembers.filter((member) =>
        failedMemberIds.has(member.memberId),
      ),
    );

    setErrorMessage(
      failedResults
        .map(({ inviteeMemberId, result }) => {
          const member = selectedMembers.find(
            ({ memberId }) => memberId === inviteeMemberId,
          );

          return `${member?.email ?? "초대 대상"}: ${getInviteResultMessage(result)}`;
        })
        .join(" "),
    );
  };

  return (
    <div className={style.inviteArea}>
      <button
        className={style.inviteButton}
        type="button"
        aria-expanded={isOpen}
        onClick={() => (isOpen ? close() : setIsOpen(true))}
      >
        이메일로 초대
      </button>

      {isOpen && (
        <div
          className={style.popover}
          role="dialog"
          aria-labelledby="project-invite-title"
        >
          <div className={style.popoverHeader}>
            <div>
              <h2
                className={style.popoverTitle}
                id="project-invite-title"
              >
                팀원 초대
              </h2>

              <p className={style.popoverDescription}>
                이메일을 추가해 여러 명을 한 번에 초대할 수 있습니다.
              </p>
            </div>

            <button
              className={style.closeButton}
              type="button"
              aria-label="초대 창 닫기"
              onClick={close}
            >
              ×
            </button>
          </div>

          <form className={style.popoverForm} onSubmit={handleSubmit}>
            <label className={style.label} htmlFor="project-invite-email">
              이메일
            </label>

            {selectedMembers.length > 0 && (
              <div
                className={style.emailList}
                aria-label="초대 대상 회원"
              >
                {selectedMembers.map((selectedMember) => (
                  <span
                    className={style.emailChip}
                    key={selectedMember.memberId}
                  >
                    <span>{selectedMember.email}</span>

                    <button
                      className={style.emailRemoveButton}
                      type="button"
                      aria-label={`${selectedMember.email} 선택 해제`}
                      onClick={() =>
                        handleMemberRemove(selectedMember.memberId)
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className={style.emailControls}>
              <input
                className={style.emailInput}
                id="project-invite-email"
                type="email"
                value={email}
                placeholder="name@example.com"
                autoComplete="email"
                autoFocus
                onChange={(event) => {
                  setEmail(event.target.value);
                  setErrorMessage("");
                  clearInvitationError();
                }}
                onKeyDown={handleKeyDown}
              />

              <button
                className={style.addButton}
                type="button"
                disabled={!trimmedEmail || isSearching}
                onClick={() => void handleEmailAdd()}
              >
                {isSearching ? "검색 중..." : "추가"}
              </button>
            </div>

            <p className={style.helperText}>
              Enter 키로 이메일을 빠르게 추가할 수 있어요.
            </p>

            {(errorMessage || invitationError) && (
              <p className={style.errorMessage} role="alert">
                {errorMessage || invitationError}
              </p>
            )}

            <button
              className={style.submitButton}
              type="submit"
              disabled={
                selectedMembers.length === 0 ||
                isSearching ||
                isInviting
              }
            >
              {isInviting
                ? "초대 중..."
                : selectedMembers.length > 0
                  ? `${selectedMembers.length}명 초대하기`
                  : "초대하기"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
