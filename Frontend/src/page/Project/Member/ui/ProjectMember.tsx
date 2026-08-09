import { useState } from "react";
import { useParams } from "react-router-dom";
import ProjectInvitePopover from "../components/ProjectInvitePopover/ProjectInvitePopover";
import ProjectRoleFilter, {
  type RoleFilter,
} from "../components/ProjectRoleFilter/ProjectRoleFilter";
import useProjectMembers from "../hooks/useProjectMembers";
import style from "../css/ProjectMember.module.css";

function formatDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
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

  const [searchKeyword, setSearchKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("ALL");

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredMembers = members.filter((member) => {
    const matchesKeyword =
      member.name.toLowerCase().includes(normalizedKeyword) ||
      member.email.toLowerCase().includes(normalizedKeyword);

    const matchesRole =
      roleFilter === "ALL" || roleFilter === member.role;

    return matchesKeyword && matchesRole;
  });

  return (
    <section className={style.page}>
      <div className={style.pageHeader}>
        <div>
          <h1 className={style.title}>팀 멤버</h1>
          <p className={style.description}>
            총 <strong>{members.length}</strong>명의 팀원이 참여 중입니다.
          </p>
        </div>

        <ProjectInvitePopover
          projectId={validProjectId}
          existingMemberIds={members.map((member) => member.memberId)}
        />
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

        <ProjectRoleFilter
          value={roleFilter}
          onChange={setRoleFilter}
        />
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
                        {isOwner ? "Owner" : "Member"}
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
