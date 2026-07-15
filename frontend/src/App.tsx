import {} from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import MainLayout from './layouts/MainLayout';
import Dashboard from './pages/Dashboard';
import Workflows from './pages/Workflows';
import WorkflowDetail from './pages/WorkflowDetail';
import WorkflowCreate from './pages/WorkflowCreate';
import WorkflowRun from './pages/WorkflowRun';
import Agents from './pages/Agents';
import AgentDetail from './pages/AgentDetail';
import Logs from './pages/Logs';
import Settings from './pages/Settings';
import Observability from './pages/Observability';

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <BrowserRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/workflows/new" element={<WorkflowCreate />} />
            <Route path="/workflows/:id" element={<WorkflowDetail />} />
            <Route path="/workflows/:id/runs/:runId" element={<WorkflowRun />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/agents/:id" element={<AgentDetail />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
