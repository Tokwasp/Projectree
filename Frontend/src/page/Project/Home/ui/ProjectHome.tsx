import ProjectIntroSection from "../components/ProjectIntroSection/ProjectIntroSection";
import RecentDecisionsSection from "../components/RecentDecisionsSection/RecentDecisionsSection";
import RecentMeetingsSection from "../components/RecentMeetingsSection/RecentMeetingsSection";
import style from "../css/ProjectHome.module.css";
import {
  mockProjectHome,
  mockRecentDecisions,
  mockRecentMeetings,
} from "../../../../mocks/ProjectHomeMocks";

export default function ProjectHome() {
  return (
    <div className={style.page}>
      <ProjectIntroSection project={mockProjectHome} />
      <RecentMeetingsSection meetings={mockRecentMeetings} />
      <RecentDecisionsSection decisions={mockRecentDecisions} />
    </div>
  );
}