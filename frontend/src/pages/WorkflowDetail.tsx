import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Input, Modal, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { PlayCircleOutlined, SaveOutlined } from '@ant-design/icons';
import WorkflowBuilder from '../components/WorkflowBuilder';
import type { AgentManifest, PlatformEdge, PlatformNode, WorkflowBuilderHandle } from '../components/WorkflowBuilder';
import { fetchApi } from '../api/client';

interface Workflow {
  id: string;
  name: string;
  description: string;
  nodes: PlatformNode[];
  edges: PlatformEdge[];
  trigger: { type: string };
  context: Record<string, unknown>;
  max_iterations: number;
  timeout: number;
  mode: string;
  terminate_on: Array<Record<string, unknown>>;
  supervisor?: Record<string, unknown> | null;
}

const statusColor: Record<string, string> = {
  completed: 'green',
  error: 'red',
  timeout: 'orange',
  max_iterations_reached: 'orange',
  running: 'blue',
};

export default function WorkflowDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [agents, setAgents] = useState<AgentManifest[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [runInput, setRunInput] = useState('');
  const builderRef = useRef<WorkflowBuilderHandle>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetchApi<Workflow>(`/api/workflows/${id}`),
      fetchApi<AgentManifest[]>('/api/agents/manifests'),
      fetchApi<any[]>(`/api/workflows/${id}/runs`),
    ])
      .then(([definition, manifests, history]) => {
        setWorkflow(definition);
        setAgents(manifests);
        setRuns(history);
      })
      .catch((error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    if (!workflow || !id) return;
    setSaving(true);
    try {
      const graph = builderRef.current?.getGraph();
      const saved = await fetchApi<Workflow>(`/api/workflows/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ workflow: { ...workflow, ...graph } }),
      });
      setWorkflow(saved);
      message.success('Workflow saved');
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (!id) return;
    try {
      const response = await fetchApi<{ run_id: string }>(`/api/workflows/${id}/run`, {
        method: 'POST',
        body: JSON.stringify({ input: runInput }),
      });
      setRunModalOpen(false);
      navigate(`/workflows/${id}/runs/${response.run_id}`);
    } catch (error: any) {
      message.error(error.message);
    }
  };

  if (loading || !workflow) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>{workflow.name}</Typography.Title>
          <Typography.Text type="secondary">{workflow.id} · {workflow.nodes.length} agents · {workflow.mode}</Typography.Text>
        </div>
        <Space>
          <Button icon={<SaveOutlined />} loading={saving} onClick={handleSave}>Save</Button>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRunModalOpen(true)}>Run</Button>
        </Space>
      </div>

      <WorkflowBuilder
        initialNodes={workflow.nodes}
        initialEdges={workflow.edges}
        agents={agents}
        ref={builderRef}
      />

      <Typography.Title level={5} style={{ marginTop: 24 }}>Run History</Typography.Title>
      <Table
        size="small"
        dataSource={runs}
        rowKey="run_id"
        pagination={false}
        columns={[
          { title: 'Run ID', dataIndex: 'run_id', key: 'run_id' },
          { title: 'Started', dataIndex: 'started_at', key: 'started_at', render: (value: string) => new Date(value).toLocaleString() },
          { title: 'Status', dataIndex: 'status', key: 'status', render: (value: string) => <Tag color={statusColor[value] || 'default'}>{value}</Tag> },
          { title: 'Iterations', key: 'iterations', render: (_: unknown, run: any) => run.result?.iterations ?? '-' },
          { title: 'Duration', key: 'duration', render: (_: unknown, run: any) => run.result?.duration_seconds ? `${run.result.duration_seconds}s` : '-' },
          { title: 'Action', key: 'action', render: (_: unknown, run: any) => <Button size="small" onClick={() => navigate(`/workflows/${id}/runs/${run.run_id}`)}>View</Button> },
        ]}
      />

      <Modal title="Run Workflow" open={runModalOpen} onOk={handleRun} onCancel={() => setRunModalOpen(false)}>
        <Input.TextArea value={runInput} onChange={(event) => setRunInput(event.target.value)} rows={5} placeholder="Describe the task for this workflow" />
      </Modal>
    </>
  );
}
