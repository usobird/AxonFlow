import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { fetchApi } from '../api/client';

interface Agent {
  id: string;
  name: string;
  role: string;
  tools?: string[];
  model?: { provider?: string; name?: string };
  model_profile_id?: string;
}

interface ModelProfile {
  id: string;
  name: string;
  config: { provider: string; name: string };
}

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const navigate = useNavigate();

  const load = async () => {
    const [agentData, profileData] = await Promise.all([
      fetchApi<Agent[]>('/api/agents'),
      fetchApi<ModelProfile[]>('/api/model-profiles'),
    ]);
    setAgents(agentData);
    setProfiles(profileData);
  };

  useEffect(() => {
    load()
      .catch((error: Error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, []);

  const openCreate = () => {
    createForm.resetFields();
    setCreateOpen(true);
  };

  const createAgent = async () => {
    const values = await createForm.validateFields();
    const agent = await fetchApi<Agent>('/api/agents', {
      method: 'POST',
      body: JSON.stringify(values),
    });
    setCreateOpen(false);
    await load();
    message.success('Agent created and started');
    navigate(`/agents/${agent.id}`);
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Agents</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} disabled={!profiles.length}>
          New Agent
        </Button>
      </Space>
      {!profiles.length && <Alert type="warning" showIcon message="Create a model profile in Settings before creating an Agent." style={{ marginBottom: 16 }} />}
      <Table<Agent>
        dataSource={agents}
        rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id' },
          { title: 'Name', dataIndex: 'name', key: 'name' },
          { title: 'Role', dataIndex: 'role', key: 'role' },
          {
            title: 'Model',
            key: 'model',
            render: (_, agent) => <Space size={4}>
              <Tag>{agent.model?.name || 'default'}</Tag>
              {agent.model_profile_id && <Tag color="blue">{profiles.find((profile) => profile.id === agent.model_profile_id)?.name || 'profile'}</Tag>}
            </Space>,
          },
          {
            title: 'Tools',
            key: 'tools',
            render: (_, agent) => agent.tools?.length || 0,
          },
          {
            title: 'Actions',
            key: 'actions',
            render: (_, agent) => (
              <Button size="small" onClick={() => navigate(`/agents/${agent.id}`)}>
                Detail
              </Button>
            ),
          },
        ]}
      />

      <Modal title="New Agent" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={createAgent} okText="Create Agent">
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="id"
            label="Agent ID"
            rules={[
              { required: true },
              { pattern: /^[a-z][a-z0-9-]{2,63}$/, message: 'Use lowercase letters, numbers, and hyphens; start with a letter.' },
            ]}
          >
            <Input placeholder="research-writer" />
          </Form.Item>
          <Form.Item name="name" label="Display name" rules={[{ required: true }]}>
            <Input placeholder="Research Writer" />
          </Form.Item>
          <Form.Item name="role" label="Role">
            <Input.TextArea rows={3} placeholder="Produces concise research summaries." />
          </Form.Item>
          <Form.Item name="model_profile_id" label="Model profile" rules={[{ required: true, message: 'Select a model profile.' }]}>
            <Select
              placeholder="Select provider and model"
              options={profiles.map((profile) => ({
                value: profile.id,
                label: `${profile.name} - ${profile.config.provider} / ${profile.config.name}`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
