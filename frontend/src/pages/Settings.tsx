import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Tabs,
  Typography,
  message,
} from 'antd';
import { DeleteOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import YamlEditor from '../components/YamlEditor';
import { fetchApi } from '../api/client';

interface Credential {
  id: string;
  name: string;
  provider: string;
  source: 'encrypted' | 'environment';
  env_var?: string;
  masked_value?: string;
}

interface Provider { id: string; label: string; default_key_env?: string; }

interface ModelProfile {
  id: string;
  name: string;
  config: {
    provider: string;
    name: string;
    temperature: number;
    max_tokens: number;
    timeout: number;
    api_base?: string;
    api_key_env?: string;
    credential_id?: string;
  };
}

interface ObservabilitySettings {
  langsmith_enabled: boolean;
  langsmith_project: string;
  langsmith_endpoint?: string;
  langsmith_credential_id?: string;
  content_policy: 'metadata_only' | 'masked_content' | 'full_content';
}

export default function Settings() {
  const [yaml, setYaml] = useState('');
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [observability, setObservability] = useState<ObservabilitySettings | null>(null);
  const [credentialModalOpen, setCredentialModalOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [credentialForm] = Form.useForm();
  const [profileForm] = Form.useForm();
  const [observabilityForm] = Form.useForm<ObservabilitySettings>();

  const load = async () => {
    const [config, credentialData, providerData, profileData, observabilityData] = await Promise.all([
      fetchApi<{ raw_yaml?: string }>('/api/config'),
      fetchApi<Credential[]>('/api/credentials'),
      fetchApi<Provider[]>('/api/credentials/catalog/providers'),
      fetchApi<ModelProfile[]>('/api/model-profiles'),
      fetchApi<ObservabilitySettings>('/api/observability/settings'),
    ]);
    setYaml(config.raw_yaml || '');
    setCredentials(credentialData);
    setProviders(providerData);
    setModelProfiles(profileData);
    setObservability(observabilityData);
  };

  useEffect(() => { load().catch((error: Error) => message.error(error.message)); }, []);

  const saveYaml = async () => {
    await fetchApi('/api/config', { method: 'PUT', body: JSON.stringify({ yaml_content: yaml }) });
    message.success('Global configuration saved');
  };

  const createCredential = async () => {
    const values = await credentialForm.validateFields();
    await fetchApi('/api/credentials', { method: 'POST', body: JSON.stringify(values) });
    setCredentialModalOpen(false);
    credentialForm.resetFields();
    await load();
    message.success('Credential encrypted and saved');
  };

  const deleteCredential = async (id: string) => {
    await fetchApi(`/api/credentials/${id}`, { method: 'DELETE' });
    await load();
    message.success('Credential deleted');
  };

  const openProfileModal = () => {
    profileForm.setFieldsValue({
      name: '',
      config: {
        provider: 'openai',
        name: '',
        temperature: 0.7,
        max_tokens: 4096,
        timeout: 60,
      },
    });
    setProfileModalOpen(true);
  };

  const createModelProfile = async () => {
    const values = await profileForm.validateFields();
    await fetchApi('/api/model-profiles', { method: 'POST', body: JSON.stringify(values) });
    setProfileModalOpen(false);
    profileForm.resetFields();
    await load();
    message.success('Model profile saved');
  };

  const deleteModelProfile = async (id: string) => {
    await fetchApi(`/api/model-profiles/${id}`, { method: 'DELETE' });
    await load();
    message.success('Model profile deleted');
  };

  const saveObservability = async () => {
    const values = await observabilityForm.validateFields();
    const result = await fetchApi<ObservabilitySettings>('/api/observability/settings', {
      method: 'PUT', body: JSON.stringify(values),
    });
    setObservability(result);
    message.success('Observability settings saved');
  };

  return (
    <>
      <Typography.Title level={3}>Settings</Typography.Title>
      <Tabs items={[
        {
          key: 'credentials',
          label: 'Credentials',
          children: <>
            <Alert
              type="info"
              showIcon
              message="Secrets are encrypted on the server and never returned to the browser."
              style={{ marginBottom: 16 }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCredentialModalOpen(true)} style={{ marginBottom: 16 }}>
              Add Credential
            </Button>
            <Table<Credential>
              dataSource={credentials}
              rowKey="id"
              pagination={false}
              columns={[
                { title: 'Name', dataIndex: 'name' },
                { title: 'Provider', dataIndex: 'provider' },
                { title: 'Source', dataIndex: 'source' },
                { title: 'Value', dataIndex: 'masked_value' },
                {
                  title: '', key: 'actions', width: 70,
                  render: (_, credential) => <Popconfirm title="Delete this credential?" onConfirm={() => deleteCredential(credential.id)}>
                    <Button danger type="text" icon={<DeleteOutlined />} aria-label="Delete credential" />
                  </Popconfirm>,
                },
              ]}
            />
          </>,
        },
        {
          key: 'observability',
          label: 'Observability',
          children: <Form form={observabilityForm} layout="vertical" initialValues={observability || undefined} style={{ maxWidth: 680 }}>
            <Form.Item name="langsmith_enabled" label="Enable LangSmith" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="langsmith_project" label="Project" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="langsmith_credential_id" label="LangSmith credential">
              <Select allowClear options={credentials.map((credential) => ({ value: credential.id, label: `${credential.name} (${credential.masked_value})` }))} />
            </Form.Item>
            <Form.Item name="langsmith_endpoint" label="Endpoint">
              <Input placeholder="https://api.smith.langchain.com" />
            </Form.Item>
            <Form.Item name="content_policy" label="Trace content policy" rules={[{ required: true }]}>
              <Select options={[
                { value: 'metadata_only', label: 'Metadata only' },
                { value: 'masked_content', label: 'Masked content (recommended)' },
                { value: 'full_content', label: 'Full content' },
              ]} />
            </Form.Item>
            <Button type="primary" icon={<SaveOutlined />} onClick={saveObservability}>Save Observability</Button>
          </Form>,
        },
        {
          key: 'profiles',
          label: 'Model Profiles',
          children: <>
            <Alert
              type="info"
              showIcon
              message="Profiles combine a provider, model, request limits, and a credential reference. Agents select one profile when created."
              style={{ marginBottom: 16 }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={openProfileModal} style={{ marginBottom: 16 }}>
              Add Model Profile
            </Button>
            <Table<ModelProfile>
              dataSource={modelProfiles}
              rowKey="id"
              pagination={false}
              columns={[
                { title: 'Name', dataIndex: 'name' },
                { title: 'Provider', render: (_, profile) => providers.find((provider) => provider.id === profile.config.provider)?.label || profile.config.provider },
                { title: 'Model', render: (_, profile) => profile.config.name },
                {
                  title: 'Credential',
                  render: (_, profile) => {
                    const credential = credentials.find((item) => item.id === profile.config.credential_id);
                    return credential ? `${credential.name} (${credential.masked_value})` : profile.config.api_key_env || 'None';
                  },
                },
                {
                  title: '', key: 'actions', width: 70,
                  render: (_, profile) => <Popconfirm title="Delete this model profile?" onConfirm={() => deleteModelProfile(profile.id)}>
                    <Button danger type="text" icon={<DeleteOutlined />} aria-label="Delete model profile" />
                  </Popconfirm>,
                },
              ]}
            />
          </>,
        },
        {
          key: 'global',
          label: 'Global YAML',
          children: <>
            <YamlEditor value={yaml} onChange={setYaml} height="520px" />
            <Button type="primary" icon={<SaveOutlined />} onClick={saveYaml} style={{ marginTop: 12 }}>Save Configuration</Button>
          </>,
        },
      ]} />

      <Modal title="Add Credential" open={credentialModalOpen} onCancel={() => setCredentialModalOpen(false)} onOk={createCredential} okText="Encrypt and Save">
        <Form form={credentialForm} layout="vertical" initialValues={{ source: 'encrypted' }}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="qwen-production" /></Form.Item>
          <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
            <Select options={providers.map((provider) => ({ value: provider.id, label: provider.label }))} />
          </Form.Item>
          <Form.Item name="source" label="Source" rules={[{ required: true }]}>
            <Select options={[{ value: 'encrypted', label: 'Paste and encrypt' }, { value: 'environment', label: 'Environment variable' }]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(previous, current) => previous.source !== current.source}>
            {({ getFieldValue }) => getFieldValue('source') === 'environment'
              ? <Form.Item name="env_var" label="Environment variable" rules={[{ required: true }]}><Input placeholder="DASHSCOPE_API_KEY" /></Form.Item>
              : <Form.Item name="secret" label="API key" rules={[{ required: true }]}><Input.Password autoComplete="new-password" /></Form.Item>}
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="Add Model Profile" open={profileModalOpen} onCancel={() => setProfileModalOpen(false)} onOk={createModelProfile} okText="Save Profile">
        <Form form={profileForm} layout="vertical">
          <Form.Item name="name" label="Profile name" rules={[{ required: true }]}>
            <Input placeholder="minimax-m3-production" />
          </Form.Item>
          <Form.Item name={['config', 'provider']} label="Provider" rules={[{ required: true }]}>
            <Select options={providers.map((provider) => ({ value: provider.id, label: provider.label }))} />
          </Form.Item>
          <Form.Item name={['config', 'name']} label="Model" rules={[{ required: true }]}>
            <Input placeholder="MiniMax-M3" />
          </Form.Item>
          <Form.Item name={['config', 'credential_id']} label="Credential">
            <Select allowClear options={credentials.map((credential) => ({ value: credential.id, label: `${credential.name} (${credential.masked_value})` }))} />
          </Form.Item>
          <Form.Item name={['config', 'api_key_env']} label="Fallback environment variable">
            <Input placeholder="MINIMAX_API_KEY" />
          </Form.Item>
          <Form.Item name={['config', 'api_base']} label="API base URL">
            <Input placeholder="https://api.minimaxi.com/v1" />
          </Form.Item>
          <Form.Item name={['config', 'temperature']} label="Temperature" rules={[{ required: true }]}>
            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name={['config', 'max_tokens']} label="Maximum output tokens" rules={[{ required: true }]}>
            <InputNumber min={1} max={1000000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name={['config', 'timeout']} label="Request timeout (seconds)" rules={[{ required: true }]}>
            <InputNumber min={1} max={3600} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
