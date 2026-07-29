import { useState } from "react";
import ProjectInvitePopover from "../components/project/ProjectInvitePopover";
import ProjectMemberList from "../components/project/ProjectMemberList";
import { mockProjectMembers } from "../mocks/ProjectMemberMocks";
import style from "../css/project/ProjectMemberPage.module.css";

type RoleFilter = "ALL" | "OWNER" | "MEMBER";

const PROJECT_OWNER_USER_ID = 1;

export default function ProjectMemberPage() {
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");

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

    const matchesRole =
      roleFilter === "ALL" || roleFilter === memberRole;

    return matchesKeyword && matchesRole;
  });

  const handleInvite = () => {
    setIsInviteOpen(false);
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
            onClick={() => setIsInviteOpen((isOpen) => !isOpen)}
          >
            이메일로 초대
          </button>

          {isInviteOpen && (
            <ProjectInvitePopover
              onClose={() => setIsInviteOpen(false)}
              onInvite={handleInvite}
            />
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
          onChange={(event) =>
            setRoleFilter(event.target.value as RoleFilter)
          }
        >
          <option value="ALL">전체 역할</option>
          <option value="OWNER">오너</option>
          <option value="MEMBER">멤버</option>
        </select>
      </div>

      <ProjectMemberList
        members={filteredMembers}
        ownerUserId={PROJECT_OWNER_USER_ID}
      />
    </section>
  );
}
