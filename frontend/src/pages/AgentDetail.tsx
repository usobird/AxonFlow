import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Typography, Tabs, Button, message, Spin, Descriptions, Tag } from 'antd';
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
