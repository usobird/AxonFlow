import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Tabs, Button, message, Spin, Descriptions, Tag, Form, Input, InputNumber, Select } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import YamlEditor from '../components/YamlEditor';
import { fetchApi } from '../api/client';
import Editor from '@monaco-editor/react';

export default function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<any>(null);
  const [yaml, setYaml] = useState('');
  const [persona, setPersona] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [credentials, setCredentials] = useState<Array<{ id: string; name: string; masked_value?: string }>>([]);
  const [providers, setProviders] = useState<Array<{ id: string; label: string }>>([]);
  const [modelForm] = Form.useForm();

  useEffect(() => {
    if (!id) return;
    fetchApi(`/api/agents/${id}`)
      .then((a) => {
        setAgent(a);
        setYaml(a.raw_yaml || JSON.stringify(a, null, 2));
        setPersona({
          'soul.md': a.persona?.soul || '',
          'user.md': a.persona?.user || '',
          'workflow.md': a.persona?.workflow || '',
        });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    Promise.all([
      fetchApi<Array<{ id: string; name: string; masked_value?: string }>>('/api/credentials'),
      fetchApi<Array<{ id: string; label: string }>>('/api/credentials/catalog/providers'),
    ]).then(([credentialData, providerData]) => {
      setCredentials(credentialData);
      setProviders(providerData);
    }).catch(console.error);
  }, []);

  const handleSaveConfig = async () => {
    try {
      await fetchApi(`/api/agents/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ yaml_content: yaml }),
      });
      message.success('Agent config saved');
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const handleSavePersona = async (fileName: string) => {
    try {
      await fetchApi(`/api/agents/${id}/persona/${fileName}`, {
        method: 'PUT',
        body: JSON.stringify({ content: persona[fileName] }),
      });
      message.success(`${fileName} saved`);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const handleSaveModel = async () => {
    try {
      const model = await modelForm.validateFields();
      await fetchApi(`/api/agents/${id}/model`, {
        method: 'PUT',
        body: JSON.stringify({ model }),
      });
      setAgent((current: any) => ({ ...current, model }));
      message.success('Model settings applied to future runs');
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Typography.Title level={3}>Agent: {agent?.name || id}</Typography.Title>

      <Descriptions bordered size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="ID">{agent?.id}</Descriptions.Item>
        <Descriptions.Item label="Role">{agent?.role}</Descriptions.Item>
        <Descriptions.Item label="Model">
          <Tag>{agent?.model?.name || 'default'}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Tools">
          {agent?.tools?.map((t: string) => <Tag key={t}>{t}</Tag>)}
        </Descriptions.Item>
      </Descriptions>

      <Tabs items={[
        {
          key: 'config',
          label: 'Config (YAML)',
          children: (
            <>
              <YamlEditor value={yaml} onChange={setYaml} height="400px" />
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveConfig} style={{ marginTop: 12 }}>
                Save Config
              </Button>
            </>
          ),
        },
        {
          key: 'model',
          label: 'Model',
          children: (
            <Form form={modelForm} initialValues={agent?.model} layout="vertical" style={{ maxWidth: 680 }}>
              <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
                <Select options={providers.map((provider) => ({ value: provider.id, label: provider.label }))} />
              </Form.Item>
              <Form.Item name="name" label="Model" rules={[{ required: true }]}><Input placeholder="qwen-plus / MiniMax-M2.5 / gpt-4o" /></Form.Item>
              <Form.Item name="credential_id" label="Credential">
                <Select allowClear placeholder="Use environment variable below" options={credentials.map((credential) => ({
                  value: credential.id,
                  label: `${credential.name} (${credential.masked_value || 'hidden'})`,
                }))} />
              </Form.Item>
              <Form.Item name="api_key_env" label="Environment variable fallback"><Input placeholder="DASHSCOPE_API_KEY" /></Form.Item>
              <Form.Item name="api_base" label="Custom API base"><Input placeholder="Optional OpenAI-compatible endpoint" /></Form.Item>
              <Form.Item name="temperature" label="Temperature"><InputNumber min={0} max={2} step={0.1} style={{ width: 160 }} /></Form.Item>
              <Form.Item name="max_tokens" label="Max tokens"><InputNumber min={1} max={100000} style={{ width: 160 }} /></Form.Item>
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveModel}>Apply Model Settings</Button>
            </Form>
          ),
        },
        ...['soul.md', 'user.md', 'workflow.md'].map(f => ({
          key: f,
          label: f,
          children: (
            <>
              <Editor
                height="300px"
                language="markdown"
                theme="vs-dark"
                value={persona[f] || ''}
                onChange={(v) => setPersona(p => ({ ...p, [f]: v || '' }))}
                options={{ minimap: { enabled: false }, fontSize: 13, wordWrap: 'on' }}
              />
              <Button type="primary" icon={<SaveOutlined />} onClick={() => handleSavePersona(f)} style={{ marginTop: 12 }}>
                Save {f}
              </Button>
            </>
          ),
        })),
      ]} />
    </>
  );
}
