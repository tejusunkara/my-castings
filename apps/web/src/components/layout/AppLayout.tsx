import { Outlet } from "react-router";

import { AppHeader } from "./AppHeader";

/** Header and page body for every logged-in page. */
export function AppLayout() {
  return (
    <>
      <AppHeader />
      <Outlet />
    </>
  );
}
