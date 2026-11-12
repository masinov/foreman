import React from "react";

import { getSession } from "../api/access";
import { clearDashboardToken } from "../api/token";
import { useResource } from "../api/useResource";
import { Menu } from "../ui/Menu";
import { paths } from "./paths";
import { Link, useRoute } from "./router";

/**
 * Who is acting, at the right end of the top bar on every page. The name is
 * the identity the server reports for this session; the menu goes to
 * workspace settings and, where signing out means something, signs out.
 *
 * Signing out is offered only for a dashboard token: it forgets the token in
 * this browser and loads the page again. With no authentication there is
 * nothing to sign out of, so there is no item.
 */
export function UserMenu() {
  const { route } = useRoute();
  const { data: session, error } = useResource(["session"], getSession);

  if (error || !session) {
    // The menu's other job does not depend on knowing the name.
    return error ? (
      <Link className="topbar__link" href={paths.workspaceSettings()}>
        Workspace settings
      </Link>
    ) : null;
  }

  const items = [
    {
      key: "settings",
      label: "Workspace settings",
      href: paths.workspaceSettings(),
      current: route.name === "workspace-settings",
    },
  ];
  if (session.can_sign_out) {
    items.push({
      key: "sign-out",
      label: "Sign out",
      onSelect: () => {
        clearDashboardToken();
        window.location.reload();
      },
    });
  }

  return (
    <Menu
      label="You"
      className="user-menu"
      triggerClassName="user-menu__trigger"
      triggerLabel={`You: ${session.name}. Workspace settings${session.can_sign_out ? ", sign out" : ""}`}
      trigger={<span className="user-menu__name">{session.name}</span>}
      items={items}
    />
  );
}
