import { Route, Routes } from "react-router-dom";
import Layout from "./layout/Layout";
import AppLayout from "./layout/AppLayout";
import Landing from "./pages/Landing";
import HomePage from "./pages/HomePage";
import ProjectCreatePage from "./pages/ProjectCreatePage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Landing />} />
      </Route>

      <Route element={<AppLayout />}>
        <Route path="/home" element={<HomePage />} />
        <Route
          path="/projects/create"
          element={<ProjectCreatePage />}
        />
      </Route>
    </Routes>
  );
}

export default App;
