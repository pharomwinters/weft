import { Text, Title } from "@mantine/core";
import { Route, Routes } from "react-router-dom";

import AccountPage from "./account/AccountPage";
import AuditLogPage from "./admin/AuditLogPage";
import InvitationsPage from "./admin/InvitationsPage";
import UsersPage from "./admin/UsersPage";
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
import WorkspaceDetailPage from "./workspaces/WorkspaceDetailPage";
import WorkspaceListPage from "./workspaces/WorkspaceListPage";

function NotFound() {
  return (
    <>
      <Title order={2}>Not found</Title>
      <Text c="dimmed">There is no page at this address.</Text>
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
        <Route path="/" element={<WorkspaceListPage />} />
        <Route path="/workspaces/:id" element={<WorkspaceDetailPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route
          path="/admin/users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/invitations"
          element={
            <RequireAdmin>
              <InvitationsPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/audit"
          element={
            <RequireAdmin>
              <AuditLogPage />
            </RequireAdmin>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
