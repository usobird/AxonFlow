import React from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Tag, Space } from 'antd';
import LiveEventLog from '../components/LiveEventLog';
import { useWebSocket } from '../api/ws';

export default function WorkflowRun() {
  const { runId } = useParams<{ id: string; runId: string }>();
  const { events, connected } = useWebSocket(runId || null);

  const lastEvent = events[events.length - 1];
  const isCompleted = lastEvent?.type === 'workflow.completed';
  const isFailed = lastEvent?.type === 'workflow.failed';

  // Extract agent flow from events
  const agents = new Set<string>();
  events.forEach(e => {
    if (e.data?.source) agents.add(e.data.source);
    if (e.data?.targets) e.data.targets.forEach((t: string) => agents.add(t));
  });

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Run: {runId}
        </Typography.Title>
        <Space>
          <Tag color={connected ? 'green' : 'red'}>
            {connected ? 'Connected' : 'Disconnected'}
          </Tag>
          {isCompleted && <Tag color="green">Completed</Tag>}
          {isFailed && <Tag color="red">Failed</Tag>}
          {!isCompleted && !isFailed && <Tag color="blue">Running</Tag>}
        </Space>
      </div>

      {/* Simple DAG visualization */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: 24,
        background: '#fff',
        borderRadius: 8,
        marginBottom: 16,
      }}>
        {Array.from(agents).map((agent, i) => (
          <React.Fragment key={agent}>
            {i > 0 && <span style={{ fontSize: 20, color: '#999' }}>→</span>}
            <Tag
              color={
                events.some(e => e.type === 'workflow.completed' && e.data?.output?.status === 'success') ? 'green' :
                events.some(e => e.data?.source === agent) ? 'green' :
                'blue'
              }
              style={{ fontSize: 14, padding: '4px 16px' }}
            >
              {agent}
            </Tag>
          </React.Fragment>
        ))}
        {agents.size === 0 && <span style={{ color: '#999' }}>Waiting for agent activity...</span>}
      </div>

      <Typography.Title level={5}>Event Log</Typography.Title>
      <LiveEventLog events={events} />
    </>
  );
}
