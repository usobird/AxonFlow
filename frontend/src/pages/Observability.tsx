import { useEffect, useState } from 'react';
import { Drawer, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { fetchApi } from '../api/client';

interface LlmSpan {
  id: string;
  run_id?: string;
  workflow_id?: string;
  agent_id?: string;
  provider: string;
  model: string;
  status: string;
  started_at: string;
  latency_ms?: number;
  input_tokens: number;
  output_tokens: number;
  input_preview?: string;
  output_preview?: string;
  error?: string;
}

export default function Observability() {
  const [spans, setSpans] = useState<LlmSpan[]>([]);
  const [workflowId, setWorkflowId] = useState('');
  const [agentId, setAgentId] = useState('');
  const [selected, setSelected] = useState<LlmSpan | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (workflowId) params.set('workflow_id', workflowId);
    if (agentId) params.set('agent_id', agentId);
    fetchApi<LlmSpan[]>(`/api/observability/spans?${params}`).then(setSpans).catch(console.error);
  }, [workflowId, agentId]);

  return <>
    <Typography.Title level={3}>LLM Traces</Typography.Title>
    <Space style={{ marginBottom: 16 }}>
      <Input allowClear placeholder="Workflow ID" value={workflowId} onChange={(event) => setWorkflowId(event.target.value)} style={{ width: 220 }} />
      <Input allowClear placeholder="Agent ID" value={agentId} onChange={(event) => setAgentId(event.target.value)} style={{ width: 220 }} />
      <Select value="latest" options={[{ value: 'latest', label: 'Latest 500 spans' }]} style={{ width: 160 }} />
    </Space>
    <Table<LlmSpan>
      dataSource={spans}
      rowKey="id"
      size="small"
      onRow={(record) => ({ onClick: () => setSelected(record) })}
      columns={[
        { title: 'Time', dataIndex: 'started_at', width: 170, render: (value) => new Date(value).toLocaleString() },
        { title: 'Agent', dataIndex: 'agent_id', width: 160, ellipsis: true },
        { title: 'Model', dataIndex: 'model', width: 210, ellipsis: true },
        { title: 'Status', dataIndex: 'status', width: 100, render: (value) => <Tag color={value === 'completed' ? 'green' : value === 'error' ? 'red' : 'blue'}>{value}</Tag> },
        { title: 'Latency', dataIndex: 'latency_ms', width: 100, render: (value) => value === null || value === undefined ? '-' : `${value} ms` },
        { title: 'Tokens', key: 'tokens', width: 120, render: (_, span) => `${span.input_tokens} / ${span.output_tokens}` },
        { title: 'Run', dataIndex: 'run_id', ellipsis: true },
      ]}
    />
    <Drawer title="LLM Call" open={Boolean(selected)} onClose={() => setSelected(null)} width={560}>
      {selected && <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div><strong>{selected.provider} / {selected.model}</strong></div>
        <div><strong>Input</strong><pre style={{ whiteSpace: 'pre-wrap' }}>{selected.input_preview || 'Not retained by the current policy'}</pre></div>
        <div><strong>Output</strong><pre style={{ whiteSpace: 'pre-wrap' }}>{selected.output_preview || 'Not retained by the current policy'}</pre></div>
        {selected.error && <div><strong>Error</strong><pre style={{ whiteSpace: 'pre-wrap', color: '#cf1322' }}>{selected.error}</pre></div>}
      </Space>}
    </Drawer>
  </>;
}
