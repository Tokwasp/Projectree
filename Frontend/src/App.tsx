import { Route, Routes } from "react-router-dom";
import Layout from "./layout/Layout";
import AppLayout from "./layout/AppLayout";

import OAuthCallback from "./components/auth/OAuthCallback";
import HomePage from "./pages/HomePage";
import Landing from "./pages/landing";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="/auth/:provider/callback" element={<OAuthCallback />} />
      </Route>

      <Route element={<AppLayout />}>
        <Route path="/home" element={<HomePage />} />
      </Route>
    </Routes>
  );
}

export default App;
