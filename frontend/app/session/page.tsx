import { Suspense } from "react";

import { SessionPageClient } from "./session-page-client";

export default function SessionPage() {
  return (
    <Suspense fallback={<main className="page-shell">Loading session...</main>}>
      <SessionPageClient />
    </Suspense>
  );
}
