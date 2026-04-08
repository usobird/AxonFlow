import { useEffect, useState } from 'react';
import { Typography, Table, Tag, Input, Select, Space } from 'antd';
import { fetchApi } from '../api/client';

const actionColors: Record<string, string> = {
  tool_call: 'orange',
  tool_error: 'red',
  llm_error: 'red',
  skill_error: 'volcano',
  routing: 'green',
  llm_summary: 'blue',
  agent_message: 'purple',
};

export default function Logs() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<{ workflow_id?: string; agent_id?: string; action?: string }>({});

  const load = () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filters.workflow_id) params.set('workflow_id', filters.workflow_id);
    if (filters.agent_id) params.set('agent_id', filters.agent_id);
    if (filters.action) params.set('action', filters.action);
    fetchApi(`/api/logs?${params}`)
      .then(setLogs)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filters]);

  return (
    <>
      <Typography.Title level={3}>Execution Logs</Typography.Title>
      <Space style={{ marginBottom: 16 }}>
        <Input placeholder="Workflow ID" allowClear onChange={e => setFilters(f => ({ ...f, workflow_id: e.target.value || undefined }))} style={{ width: 200 }} />
        <Input placeholder="Agent ID" allowClear onChange={e => setFilters(f => ({ ...f, agent_id: e.target.value || undefined }))} style={{ width: 200 }} />
        <Select placeholder="Action" allowClear onChange={v => setFilters(f => ({ ...f, action: v }))} style={{ width: 160 }}
          options={['tool_call', 'tool_error', 'llm_error', 'routing', 'llm_summary', 'agent_message'].map(a => ({ label: a, value: a }))}
        />
      </Space>
      <Table
        dataSource={logs}
        rowKey={(_: any, i: any) => String(i)}
        loading={loading}
        pagination={{ pageSize: 50 }}
        size="small"
        columns={[
          { title: 'Time', dataIndex: 'timestamp', key: 'time', width: 200, render: (t: string) => new Date(t).toLocaleString() },
          { title: 'Workflow', dataIndex: 'workflow_id', key: 'wf', width: 150, ellipsis: true },
          { title: 'Agent', dataIndex: 'agent_id', key: 'agent', width: 150 },
          { title: 'Action', dataIndex: 'action', key: 'action', width: 120, render: (a: string) => <Tag color={actionColors[a] || 'default'}>{a}</Tag> },
          { title: 'Tool', dataIndex: 'tool_name', key: 'tool', width: 120 },
          { title: 'Round', dataIndex: 'round', key: 'round', width: 70 },
          { title: 'Result', dataIndex: 'result', key: 'result', ellipsis: true },
          { title: 'Error', dataIndex: 'error', key: 'error', ellipsis: true, render: (e: string) => e && <Tag color="red">{e}</Tag> },
        ]}
      />
    </>
  );
}
