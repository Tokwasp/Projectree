import { useParams } from "react-router-dom";
import style from "../css/ProjectMeeting.module.css";
import MeetingPrejoinModal from "../components/MeetingPrejoinModal/MeetingPrejoinModal";
import { useMeetingStore } from "../../../../store/meetingStore";

export default function ProjectMeeting() {
  const { projectId } = useParams<{ projectId: string }>();
  const phase = useMeetingStore((state) => state.phase);

  if (phase === "live") return null;

  return (
    <div className={style.container}>
      {phase === "connecting" ? (
        <p className={style.connecting}>회의에 연결하는 중입니다…</p>
      ) : (
        <MeetingPrejoinModal projectId={Number(projectId)} />
      )}
    </div>
  );
}
