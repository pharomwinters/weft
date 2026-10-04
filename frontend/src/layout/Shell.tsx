import { AppShell, Button, Container, Group, Text, Title } from "@mantine/core";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { request } from "../api/client";
import { useSession } from "../auth/SessionProvider";
import { APP_NAME } from "../constants";

const LINKS = [
  { to: "/", label: "Workspaces" },
  { to: "/account", label: "Account" },
];
const ADMIN_LINKS = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/invitations", label: "Invitations" },
  { to: "/admin/audit", label: "Audit log" },
];

export default function Shell() {
  const session = useSession();
  const navigate = useNavigate();
  const links = session.user?.is_instance_admin ? [...LINKS, ...ADMIN_LINKS] : LINKS;

  async function signOut() {
    try {
      await request("POST", "/auth/logout");
    } finally {
      await session.refresh();
      navigate("/login");
    }
  }

  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="lg" wrap="nowrap">
            <Title order={4}>{APP_NAME}</Title>
            <Group component="nav" gap="md" aria-label="Main">
              {links.map((link) => (
                <NavLink key={link.to} to={link.to} end={link.to === "/"}>
                  {link.label}
                </NavLink>
              ))}
            </Group>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Text size="sm">{session.user?.email}</Text>
            <Button variant="default" size="xs" onClick={() => void signOut()}>
              Sign out
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg">
          <Outlet />
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
