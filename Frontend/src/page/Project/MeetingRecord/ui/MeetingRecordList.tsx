import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import useMeetingRecords from "../hooks/useMeetingRecords";
import style from "../css/MeetingRecordList.module.css";

function formatMeetingDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function MeetingRecordList() {
  const { projectId } = useParams<{ projectId: string }>();
  const parsedProjectId = Number(projectId);
  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;

  const [page, setPage] = useState(0);
  const { data, isLoading, error } = useMeetingRecords(
    validProjectId,
    page,
  );

  const records = data?.records ?? [];
  const totalPages = data?.totalPages ?? 0;

  return (
    <div className={style.page}>
      <div className={style.heading}>
        <div>
          <h1>전체 회의록</h1>
          <p>프로젝트에서 작성된 회의록을 확인해보세요.</p>
        </div>

        {!isLoading && !error && (
          <span className={style.recordCount}>
            총 {data?.totalElements ?? 0}개
          </span>
        )}
      </div>

      {isLoading ? (
        <p className={style.stateMessage}>
          회의록을 불러오는 중입니다.
        </p>
      ) : error ? (
        <p className={style.stateMessage} role="alert">
          {error}
        </p>
      ) : records.length === 0 ? (
        <p className={style.stateMessage}>
          아직 작성된 회의록이 없습니다.
        </p>
      ) : (
        <>
          <ul className={style.recordList}>
            {records.map((record) => (
              <li key={record.meetingRecordId}>
                <Link
                  className={style.recordItem}
                  to={`/projects/${validProjectId}/meetings/${record.meetingId}/record`}
                >
                  <div className={style.recordInfo}>
                    <strong>{record.title}</strong>
                    <time dateTime={record.meetingDate}>
                      {formatMeetingDate(record.meetingDate)}
                    </time>
                  </div>

                  <span aria-hidden="true">›</span>
                </Link>
              </li>
            ))}
          </ul>

          {totalPages > 1 && (
            <nav
              className={style.pagination}
              aria-label="회의록 페이지"
            >
              <button
                disabled={page === 0}
                onClick={() => setPage((current) => current - 1)}
                type="button"
              >
                이전
              </button>

              <span>
                {page + 1} / {totalPages}
              </span>

              <button
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((current) => current + 1)}
                type="button"
              >
                다음
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}