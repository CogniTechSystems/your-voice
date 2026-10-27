import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { Layout } from "./components/Layout";
import { AgentsPage } from "./pages/AgentsPage";
import { DeploymentsPage } from "./pages/DeploymentsPage";
import { JobFormPage } from "./pages/JobFormPage";
import { JobsPage } from "./pages/JobsPage";
import { JobWorkspacePage } from "./pages/JobWorkspacePage";
import { ModelsPage } from "./pages/ModelsPage";
import { RuntimesPage } from "./pages/RuntimesPage";
import { SamplesPage } from "./pages/SamplesPage";
import "./styles.css";

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/jobs" replace /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "jobs/new", element: <JobFormPage /> },
      { path: "jobs/:jobId", element: <JobWorkspacePage /> },
      { path: "jobs/:jobId/edit", element: <JobFormPage /> },
      { path: "samples", element: <SamplesPage /> },
      { path: "agents", element: <AgentsPage /> },
      { path: "admin/models", element: <ModelsPage /> },
      { path: "admin/runtimes", element: <RuntimesPage /> },
      { path: "admin/deployments", element: <DeploymentsPage /> },
      { path: "*", element: <Navigate to="/jobs" replace /> },
    ],
  },
]);

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element not found.");
}

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
