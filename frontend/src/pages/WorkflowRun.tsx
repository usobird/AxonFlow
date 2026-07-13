import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Space, Spin, Tag, Typography } from 'antd';
import WorkflowRunCanvas from '../components/WorkflowRunCanvas';
import type { PlatformEdge, PlatformNode } from '../components/WorkflowBuilder';
import LiveEventLog from '../components/LiveEventLog';
import { fetchApi } from '../api/client';
import { useWebSocket } from '../api/ws';
import type { WsEvent } from '../api/ws';

interface WorkflowDefinition {
  nodes: PlatformNode[];
  edges: PlatformEdge[];
}

interface RunDetail {
  status: string;
  node_runs: Array<{ node_id: string; status: string }>;
  events: WsEvent[];
}

export default function WorkflowRun() {
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const [workflow, setWorkflow] = useState<WorkflowDefinition | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const { events: liveEvents, connected } = useWebSocket(runId || null);

  useEffect(() => {
    if (!id || !runId) return;
    Promise.all([
      fetchApi<WorkflowDefinition>(`/api/workflows/${id}`),
      fetchApi<RunDetail>(`/api/workflows/${id}/runs/${runId}`),
    ]).then(([definition, detail]) => {
      setWorkflow(definition);
      setRun(detail);
    }).catch(console.error);
  }, [id, runId]);

  const events = useMemo(() => {
    const existing = run?.events || [];
    return [...existing, ...liveEvents];
  }, [run, liveEvents]);
  const nodeRuns = useMemo(() => {
    const statuses = new Map((run?.node_runs || []).map((nodeRun) => [nodeRun.node_id, nodeRun.status]));
    events.forEach((event) => {
      const nodeId = event.data?.node_id;
      if (!nodeId) return;
      if (event.type === 'node.task_assigned') statuses.set(nodeId, 'queued');
      if (event.type === 'node.task_started') statuses.set(nodeId, 'running');
      if (event.type === 'node.result_ready') statuses.set(nodeId, 'completed');
      if (event.type === 'node.error') statuses.set(nodeId, 'error');
    });
    return Array.from(statuses, ([node_id, status]) => ({ node_id, status }));
  }, [events, run]);
  const latestStatus = liveEvents.findLast?.((event) => event.type.startsWith('workflow.'))?.type === 'workflow.completed'
    ? 'completed'
    : liveEvents.findLast?.((event) => event.type === 'workflow.failed')
      ? 'error'
      : run?.status || 'running';

  if (!workflow || !run) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Run: {runId}</Typography.Title>
        <Space>
          <Tag color={connected ? 'green' : 'default'}>{connected ? 'Live' : 'Reconnecting'}</Tag>
          <Tag color={latestStatus === 'completed' ? 'green' : latestStatus === 'error' ? 'red' : 'blue'}>{latestStatus}</Tag>
        </Space>
      </div>
      <WorkflowRunCanvas nodes={workflow.nodes} edges={workflow.edges} nodeRuns={nodeRuns} />
      <Typography.Title level={5} style={{ marginTop: 20 }}>Event Log</Typography.Title>
      <LiveEventLog events={events} />
    </>
  );
}
