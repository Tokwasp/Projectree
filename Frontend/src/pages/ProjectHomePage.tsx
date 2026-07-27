import ProjectIntroSection from "../components/project/ProjectIntroSection";
import RecentDecisionsSection from "../components/project/RecentDecisionsSection";
import RecentMeetingsSection from "../components/project/RecentMeetingsSection";
import style from "../css/project/ProjectHomePage.module.css";
import {
  mockProjectHome,
  mockRecentDecisions,
  mockRecentMeetings,
} from "../mocks/ProjectHomeMocks";

export default function ProjectHomePage() {
  return (
    <div className={style.page}>
      <ProjectIntroSection project={mockProjectHome} />
      <RecentMeetingsSection meetings={mockRecentMeetings} />
      <RecentDecisionsSection decisions={mockRecentDecisions} />
    </div>
  );
}