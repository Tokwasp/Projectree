import { Route, Routes } from "react-router-dom";
import Layout from "./layout/Layout";
import AppLayout from "./layout/AppLayout";
import ProjectLayout from "./layout/ProjectLayout";

import OAuthCallback from "./page/Auth/OAuthCallback/OAuthCallback";
import Landing from "./page/Landing/ui/Landing";
import Home from "./page/Home/ui/Home";
import MyPage from "./page/MyPage/ui/MyPage";
import ProjectList from "./page/Project/List/ui/ProjectList";
import ProjectCreate from "./page/Project/Create/ui/ProjectCreate";
import ProjectHome from "./page/Project/Home/ui/ProjectHome";
import InvitationLanding from "./page/Project/Invitation/ui/InvitationLanding";
import ProjectMember from "./page/Project/Member/ui/ProjectMember";
import ProjectMeeting from "./page/Project/Meeting/ui/ProjectMeeting";
import ProjectTree from "./page/Project/Tree/ui/ProjectTree";
import MeetingOverlay from "./page/Project/Meeting/components/MeetingOverlay/MeetingOverlay";

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="/auth/:provider/callback" element={<OAuthCallback />} />
          <Route path="/invitations/:token" element={<InvitationLanding />} />
        </Route>

        <Route element={<AppLayout />}>
          <Route path="/home" element={<Home />} />
          <Route path="/projects/create" element={<ProjectCreate />} />
          <Route path="/mypage" element={<MyPage />} />
          <Route path="/projects" element={<ProjectList />} />
        </Route>

        <Route path="/projects/:projectId" element={<ProjectLayout />}>
          <Route index element={<ProjectHome />} />
          <Route path="members" element={<ProjectMember />} />
          <Route path="meeting" element={<ProjectMeeting />} />
          <Route path="tree" element={<ProjectTree />} />
        </Route>
      </Routes>

      <MeetingOverlay />
    </>
  );
}

export default App;
