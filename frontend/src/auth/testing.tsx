import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { renderApp } from "../test/utils";

/** Render one page at its route, with stand-ins for wherever it may navigate. */
export function renderPage(page: React.ReactNode, route: string, path: string) {
  return renderApp(
    <Routes>
      <Route path={route} element={page} />
      <Route path="*" element={<p>Another page</p>} />
    </Routes>,
    { path },
  );
}

export function location(): string | null {
  return screen.getByTestId("location").textContent;
}

/** Matches a field's label, with or without the asterisk a required one gets. */
export function labelled(label: string): RegExp {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${escaped}( \\*)?$`);
}

export async function type(label: string | RegExp, text: string) {
  const matcher = typeof label === "string" ? labelled(label) : label;
  await userEvent.type(await screen.findByLabelText(matcher), text);
}

export async function click(name: string | RegExp) {
  await userEvent.click(await screen.findByRole("button", { name }));
}

/** Fill both new-password inputs (labels "X" and "X again"). */
export async function typeNewPassword(first: string, second = first, label = "Password") {
  await type(new RegExp(`^${label}\\b(?!.*again)`, "i"), first);
  await type(new RegExp(`^${label} again`, "i"), second);
}
