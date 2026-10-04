import { Text, Title } from "@mantine/core";
import { Route, Routes } from "react-router-dom";

import EnrolPage from "./auth/EnrolPage";
import ForcedPasswordPage from "./auth/ForcedPasswordPage";
import {
  RequireAdmin,
  RequireAnonymous,
  RequirePartial,
  RequireVerified,
} from "./auth/guards";
import InvitationPage from "./auth/InvitationPage";
import LoginPage from "./auth/LoginPage";
import ResetPage from "./auth/ResetPage";
import SetupPage from "./auth/SetupPage";
import VerifyPage from "./auth/VerifyPage";
import Shell from "./layout/Shell";

/** Stands in for a screen until its task builds it. */
function Placeholder({ title }: { title: string }) {
  return (
    <>
      <Title order={2}>{title}</Title>
      <Text c="dimmed">This screen is not built yet.</Text>
    </>
  );
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/setup" element={<SetupPage />} />
      <Route
        path="/login"
        element={
          <RequireAnonymous>
            <LoginPage />
          </RequireAnonymous>
        }
      />
      <Route
        path="/verify"
        element={
          <RequirePartial step="verify">
            <VerifyPage />
          </RequirePartial>
        }
      />
      <Route
        path="/enrol"
        element={
          <RequirePartial step="enrol">
            <EnrolPage />
          </RequirePartial>
        }
      />
      <Route
        path="/change-password"
        element={
          <RequirePartial step="change_password">
            <ForcedPasswordPage />
          </RequirePartial>
        }
      />
      <Route path="/invite/:token" element={<InvitationPage />} />
      <Route path="/reset/:token" element={<ResetPage />} />
      <Route
        element={
          <RequireVerified>
            <Shell />
          </RequireVerified>
        }
      >
        <Route path="/" element={<Placeholder title="Workspaces" />} />
        <Route path="/workspaces/:id" element={<Placeholder title="Workspace" />} />
        <Route path="/account" element={<Placeholder title="Account" />} />
        <Route
          path="/admin/users"
          element={
            <RequireAdmin>
              <Placeholder title="Users" />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/invitations"
          element={
            <RequireAdmin>
              <Placeholder title="Invitations" />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <RequireAdmin>
              <Placeholder title="Audit log" />
            </RequireAdmin>
          }
        />
        <Route path="*" element={<Placeholder title="Not found" />} />
      </Route>
    </Routes>
  );
}
