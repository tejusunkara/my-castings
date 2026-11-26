import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { logout } from "../../api/auth";
import { sourceColor, sourceName } from "../../lib/sources";
import styles from "./AppHeader.module.css";

const LEGEND = ["casting_networks", "backstage", "actors_access"];

export function Logo() {
  return (
    <span className={styles.logo}>
      All<span className={styles.logoAccent}>Castings</span>
    </span>
  );
}

export function AppHeader() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const signOut = useMutation({
    mutationFn: logout,
    onSettled: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  return (
    <header className={styles.header}>
      <Logo />
      <div className={styles.right}>
        <ul className={styles.legend} aria-label="Sources">
          {LEGEND.map((key) => (
            <li key={key} className={styles.pill} style={{ background: sourceColor(key) }}>
              {sourceName(key)}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className={styles.logout}
          onClick={() => signOut.mutate()}
          disabled={signOut.isPending}
        >
          Log out
        </button>
      </div>
    </header>
  );
}
