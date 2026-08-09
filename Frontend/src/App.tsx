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
import ProjectManagement from "./page/Project/Management/ui/ProjectManagement";
import PrivateLayout from "./layout/PrivateLayout";
import ProjectMeeting from "./page/Project/Meeting/ui/ProjectMeeting";
import ProjectTree from "./page/Project/Tree/ui/ProjectTree";
import MeetingRecordList from "./page/Project/MeetingRecord/ui/MeetingRecordList";
import MeetingRecordDetail from "./page/Project/MeetingRecord/ui/MeetingRecordDetail";
import MeetingOverlay from "./page/Project/Meeting/components/MeetingOverlay/MeetingOverlay";
import ToastViewport from "./components/Toast/ToastViewport";

function App() {
  return (
    <>
      <Routes>
        <Route path="/auth/:provider/callback" element={<OAuthCallback />} />
        <Route path="/invitations/:token" element={<InvitationLanding />} />

        <Route path="/" element={<Layout />}>
          <Route index element={<Landing />} />
        </Route>

        <Route element={<PrivateLayout />}>
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
            <Route path="meetings/records" element={<MeetingRecordList />} />
            <Route
              path="meetings/:meetingId/record"
              element={<MeetingRecordDetail />}
            />
            <Route path="tree" element={<ProjectTree />} />
            <Route path="settings" element={<ProjectManagement />} />
          </Route>
        </Route>
      </Routes>
      <MeetingOverlay />
      <ToastViewport />
    </>
  );
}

export default App;
