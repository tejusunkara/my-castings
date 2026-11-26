import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { useEffect } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { App } from "../App";
import { createQueryClient } from "../queryClient";

// The router's current location, recorded after each render for assertions.
export const probe: { location?: ReturnType<typeof useLocation> } = {};

function LocationProbe() {
  const current = useLocation();
  useEffect(() => {
    probe.location = current;
  }, [current]);
  return null;
}

export function renderApp(path = "/") {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
