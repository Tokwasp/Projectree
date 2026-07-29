import type { ProjectMemberSummary } from "../../types/ProjectMember";
import style from "../../css/project/ProjectMemberList.module.css";

interface ProjectMemberListProps {
  members: ProjectMemberSummary[];
  ownerUserId: number;
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function ProjectMemberList({
  members,
  ownerUserId,
}: ProjectMemberListProps) {
  if (members.length === 0) {
    return (
      <div className={style.empty}>
        조건에 맞는 팀원이 없습니다.
      </div>
    );
  }

  return (
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
          {members.map((member) => {
            const isOwner = member.userId === ownerUserId;

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

                    <strong className={style.name}>
                      {member.name}
                    </strong>
                  </div>
                </td>

                <td className={style.email}>
                  {member.email}
                </td>

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
  );
}
