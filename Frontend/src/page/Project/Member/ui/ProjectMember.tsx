import {
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useParams } from "react-router-dom";
import type { MemberSearchResponse } from "../api/projectInvitationApi";
import useProjectInvitation from "../hooks/useProjectInvitation";
import useProjectMembers from "../hooks/useProjectMembers";
import style from "../css/ProjectMember.module.css";

type RoleFilter = "ALL" | "OWNER" | "MEMBER";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_INVITE_COUNT = 10;

function formatDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

function getInviteResultMessage(result: string) {
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

export default function ProjectMember() {
  const { projectId } = useParams<{ projectId: string }>();
  const parsedProjectId = Number(projectId);
  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;

  const { members, isLoading, error } =
    useProjectMembers(validProjectId);
  const {
    searchMember,
    inviteMembers,
    isSearching,
    isInviting,
    error: invitationError,
    clearError: clearInvitationError,
  } = useProjectInvitation();

  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");
  const [email, setEmail] = useState("");
  const [selectedMembers, setSelectedMembers] = useState<
    MemberSearchResponse[]
  >([]);
  const [errorMessage, setErrorMessage] = useState("");

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredMembers = members.filter((member) => {
    const matchesKeyword =
      member.name.toLowerCase().includes(normalizedKeyword) ||
      member.email.toLowerCase().includes(normalizedKeyword);

    const matchesRole =
      roleFilter === "ALL" || roleFilter === member.role;

    return matchesKeyword && matchesRole;
  });

  const trimmedEmail = email.trim().toLowerCase();

  const closeInvite = () => {
    setIsInviteOpen(false);
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

    if (
      members.some(
        (member) => member.memberId === foundMember.memberId,
      )
    ) {
      setErrorMessage("이미 프로젝트에 참여 중인 회원입니다.");
      return;
    }

    setSelectedMembers((selectedMembers) => [
      ...selectedMembers,
      foundMember,
    ]);
    setEmail("");
    setErrorMessage("");
  };

  const handleMemberRemove = (memberId: number) => {
    setSelectedMembers((selectedMembers) =>
      selectedMembers.filter(
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

  const handleInviteSubmit = async (
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    if (validProjectId === null || selectedMembers.length === 0) {
      return;
    }

    const response = await inviteMembers(
      validProjectId,
      selectedMembers.map((member) => member.memberId),
    );

    if (!response) {
      return;
    }

    const failedResults = response.results.filter(
      ({ result }) => result !== "INVITED" && result !== "RESENT",
    );

    if (failedResults.length === 0) {
      closeInvite();
      return;
    }

    const failedMemberIds = new Set(
      failedResults.map(({ inviteeMemberId }) => inviteeMemberId),
    );

    setSelectedMembers((selectedMembers) =>
      selectedMembers.filter((member) =>
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
    <section className={style.page}>
      <div className={style.pageHeader}>
        <div>
          <h1 className={style.title}>팀 멤버</h1>
          <p className={style.description}>
            총 {members.length}명의 팀원이 참여 중입니다.
          </p>
        </div>

        <div className={style.inviteArea}>
          <button
            className={style.inviteButton}
            type="button"
            aria-expanded={isInviteOpen}
            onClick={() =>
              isInviteOpen ? closeInvite() : setIsInviteOpen(true)
            }
          >
            이메일로 초대
          </button>

          {isInviteOpen && (
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
                  onClick={closeInvite}
                >
                  ×
                </button>
              </div>

              <form
                className={style.popoverForm}
                onSubmit={handleInviteSubmit}
              >
                <label
                  className={style.label}
                  htmlFor="project-invite-email"
                >
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
      </div>

      <div className={style.toolbar}>
        <input
          className={style.searchInput}
          type="search"
          value={searchKeyword}
          placeholder="이름 또는 이메일 검색"
          aria-label="팀원 검색"
          onChange={(event) => setSearchKeyword(event.target.value)}
        />

        <select
          className={style.roleFilter}
          value={roleFilter}
          aria-label="팀원 역할 필터"
          onChange={(event) => setRoleFilter(event.target.value as RoleFilter)}
        >
          <option value="ALL">전체 역할</option>
          <option value="OWNER">오너</option>
          <option value="MEMBER">멤버</option>
        </select>
      </div>

      {isLoading ? (
        <div className={style.empty}>
          팀원 목록을 불러오는 중입니다.
        </div>
      ) : error ? (
        <div className={style.empty} role="alert">
          {error}
        </div>
      ) : filteredMembers.length === 0 ? (
        <div className={style.empty}>조건에 맞는 팀원이 없습니다.</div>
      ) : (
        <div className={style.tableContainer}>
          <table className={style.table}>
            <thead>
              <tr>
                <th>이름</th>
                <th>이메일</th>
                <th>역할</th>
                <th>참여일</th>
              </tr>
            </thead>

            <tbody>
              {filteredMembers.map((member) => {
                const isOwner = member.role === "OWNER";

                return (
                  <tr key={member.memberId}>
                    <td>
                      <div className={style.member}>
                        <div className={style.avatar}>
                          <span>{member.name.slice(0, 1)}</span>
                        </div>

                        <strong className={style.name}>{member.name}</strong>
                      </div>
                    </td>

                    <td className={style.email}>{member.email}</td>

                    <td>
                      <span
                        className={`${style.roleBadge} ${
                          isOwner ? style.owner : style.memberRole
                        }`}
                      >
                        {isOwner ? "오너" : "멤버"}
                      </span>
                    </td>

                    <td className={style.joinedAt}>
                      {formatDate(member.joinedAt)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
