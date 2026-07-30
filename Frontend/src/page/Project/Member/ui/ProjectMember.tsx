import {
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { mockProjectMembers } from "../../../../mocks/ProjectMemberMocks";
import style from "../css/ProjectMember.module.css";

type RoleFilter = "ALL" | "OWNER" | "MEMBER";

const PROJECT_OWNER_USER_ID = 1;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_INVITE_COUNT = 10;

function formatDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function ProjectMember() {
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");
  const [email, setEmail] = useState("");
  const [selectedEmails, setSelectedEmails] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");

  const activeMembers = mockProjectMembers.filter(
    (member) => member.status === "ACTIVE" && !member.leftAt,
  );

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredMembers = activeMembers.filter((member) => {
    const matchesKeyword =
      member.name.toLowerCase().includes(normalizedKeyword) ||
      member.email.toLowerCase().includes(normalizedKeyword);

    const memberRole =
      member.userId === PROJECT_OWNER_USER_ID ? "OWNER" : "MEMBER";

    const matchesRole = roleFilter === "ALL" || roleFilter === memberRole;

    return matchesKeyword && matchesRole;
  });

  const trimmedEmail = email.trim().toLowerCase();

  const closeInvite = () => {
    setIsInviteOpen(false);
    setEmail("");
    setSelectedEmails([]);
    setErrorMessage("");
  };

  const handleEmailAdd = () => {
    if (!trimmedEmail) {
      return;
    }

    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setErrorMessage("올바른 이메일 주소를 입력해주세요.");
      return;
    }

    if (selectedEmails.includes(trimmedEmail)) {
      setErrorMessage("이미 추가한 이메일입니다.");
      return;
    }

    if (selectedEmails.length >= MAX_INVITE_COUNT) {
      setErrorMessage(
        `한 번에 최대 ${MAX_INVITE_COUNT}명까지 초대할 수 있습니다.`,
      );
      return;
    }

    setSelectedEmails((emails) => [...emails, trimmedEmail]);
    setEmail("");
    setErrorMessage("");
  };

  const handleEmailRemove = (emailToRemove: string) => {
    setSelectedEmails((emails) =>
      emails.filter((selectedEmail) => selectedEmail !== emailToRemove),
    );
    setErrorMessage("");
  };

  // Enter·쉼표로도 이메일을 추가할 수 있게 한다
  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      handleEmailAdd();
    }
  };

  const handleInviteSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (selectedEmails.length === 0) {
      return;
    }

    closeInvite();
  };

  return (
    <section className={style.page}>
      <div className={style.pageHeader}>
        <div>
          <h1 className={style.title}>팀 멤버</h1>
          <p className={style.description}>
            총 {activeMembers.length}명의 팀원이 참여 중입니다.
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

                {selectedEmails.length > 0 && (
                  <div
                    className={style.emailList}
                    aria-label="초대 대상 이메일"
                  >
                    {selectedEmails.map((selectedEmail) => (
                      <span className={style.emailChip} key={selectedEmail}>
                        <span>{selectedEmail}</span>

                        <button
                          className={style.emailRemoveButton}
                          type="button"
                          aria-label={`${selectedEmail} 선택 해제`}
                          onClick={() => handleEmailRemove(selectedEmail)}
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
                    }}
                    onKeyDown={handleKeyDown}
                  />

                  <button
                    className={style.addButton}
                    type="button"
                    disabled={!trimmedEmail}
                    onClick={handleEmailAdd}
                  >
                    추가
                  </button>
                </div>

                <p className={style.helperText}>
                  Enter 키로 이메일을 빠르게 추가할 수 있어요.
                </p>

                {errorMessage && (
                  <p className={style.errorMessage}>{errorMessage}</p>
                )}

                <button
                  className={style.submitButton}
                  type="submit"
                  disabled={selectedEmails.length === 0}
                >
                  {selectedEmails.length > 0
                    ? `${selectedEmails.length}명 초대하기`
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

      {filteredMembers.length === 0 ? (
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
                const isOwner = member.userId === PROJECT_OWNER_USER_ID;

                return (
                  <tr key={member.projectMemberId}>
                    <td>
                      <div className={style.member}>
                        <div className={style.avatar}>
                          {member.profileImageUrl ? (
                            <img
                              src={member.profileImageUrl}
                              alt={`${member.name} 프로필`}
                            />
                          ) : (
                            <span>{member.name.slice(0, 1)}</span>
                          )}
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
