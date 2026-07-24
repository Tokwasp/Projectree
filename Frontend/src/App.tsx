import { Route, Routes } from "react-router-dom";
import Layout from "./layout/Layout";
import Landing from "./pages/Landing";
import OAuthCallback from "./components/auth/OAuthCallback";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="/auth/:provider/callback" element={<OAuthCallback />} />
      </Route>
    </Routes>
  );
}

export default App;
