import Link from "next/link";

import { GithubIcon } from "./icons";
import styles from "./site-chrome.module.css";

const REPO_URL = "https://github.com/Aaron-Shrike/todo-ia";

/** Shared nav bar — identical on `/` and `/acerca` so the two pages read as one product. */
export function SiteHeader() {
  return (
    <nav className={styles.nav} aria-label="Navegación principal">
      <Link href="/" className={styles.brand}>
        todo-ia
      </Link>
      <div className={styles.navLinks}>
        <Link href="/acerca" className={styles.navLink}>
          Acerca de
        </Link>
        <a
          className={styles.navLink}
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          <GithubIcon width={18} height={18} />
          Código
        </a>
      </div>
    </nav>
  );
}

/** Shared footer — identical on `/` and `/acerca`. */
export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <span>todo-ia — validación semántica de frases duplicadas.</span>
      <Link href="/">Lista de frases</Link>
    </footer>
  );
}
