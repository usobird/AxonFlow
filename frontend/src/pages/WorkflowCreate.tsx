import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Form, Input, InputNumber, Spin, Typography, message } from 'antd';
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import WorkflowBuilder from '../components/WorkflowBuilder';
import type { AgentManifest, PlatformNode, WorkflowBuilderHandle } from '../components/WorkflowBuilder';
import { fetchApi } from '../api/client';

interface WorkflowCreateValues {
  id: string;
  name: string;
  description?: string;
  max_iterations: number;
  timeout: number;
}

interface WorkflowResponse {
  id: string;
}

function completionConditions(nodes: PlatformNode[]) {
  return nodes
    .filter((node) => node.config.terminate_on_success === true)
    .map((node) => ({ agent: node.agent_id, status: 'success' }));
}

export default function WorkflowCreate() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<WorkflowCreateValues>();
  const builderRef = useRef<WorkflowBuilderHandle>(null);

  useEffect(() => {
    fetchApi<AgentManifest[]>('/api/agents/manifests')
      .then(setAgents)
      .catch((error: Error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, []);

  const createWorkflow = async () => {
    try {
      const values = await form.validateFields();
      const graph = builderRef.current?.getGraph();
      if (!graph?.nodes.length) {
        message.error('Drag at least one Agent onto the canvas.');
        return;
      }
      const terminateOn = completionConditions(graph.nodes);
      if (!terminateOn.length) {
        message.error('Select at least one Agent that completes the workflow on success.');
        return;
      }
      setSaving(true);
      const workflow = await fetchApi<WorkflowResponse>('/api/workflows', {
        method: 'POST',
        body: JSON.stringify({
          workflow: {
            id: values.id,
            name: values.name,
            description: values.description || '',
            nodes: graph.nodes,
            edges: graph.edges,
            trigger: { type: 'manual' },
            context: {},
            max_iterations: values.max_iterations,
            timeout: values.timeout,
            mode: 'flat',
            terminate_on: terminateOn,
            supervisor: null,
          },
        }),
      });
      message.success('Workflow created');
      navigate(`/workflows/${workflow.id}`);
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        <div>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/workflows')} style={{ marginLeft: -8 }}>
            Workflows
          </Button>
          <Typography.Title level={3} style={{ margin: 0 }}>New Workflow</Typography.Title>
        </div>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={createWorkflow}>
          Create Workflow
        </Button>
      </div>

      <Form form={form} layout="vertical" initialValues={{ max_iterations: 10, timeout: 3600 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
          <Form.Item name="id" label="Workflow ID" rules={[{ required: true }, { pattern: /^[a-z][a-z0-9-]{2,63}$/, message: 'Use lowercase letters, numbers, and hyphens; start with a letter.' }]}>
            <Input placeholder="content-review-flow" />
          </Form.Item>
          <Form.Item name="name" label="Workflow name" rules={[{ required: true }]}>
            <Input placeholder="Content Review Flow" />
          </Form.Item>
          <Form.Item name="max_iterations" label="Maximum steps" rules={[{ required: true }]}>
            <InputNumber min={1} max={1000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="timeout" label="Timeout (seconds)" rules={[{ required: true }]}>
            <InputNumber min={1} max={86400} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} placeholder="What this workflow accomplishes." />
        </Form.Item>
      </Form>

      <WorkflowBuilder initialNodes={[]} initialEdges={[]} agents={agents} ref={builderRef} />
    </>
  );
}
