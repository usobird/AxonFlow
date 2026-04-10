import { useEffect, useState } from 'react';
import { Typography, Button, message, Spin } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import YamlEditor from '../components/YamlEditor';
import { fetchApi } from '../api/client';

export default function Settings() {
  const [yaml, setYaml] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApi('/api/config')
      .then(data => setYaml(data.raw_yaml || JSON.stringify(data, null, 2)))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    try {
      await fetchApi('/api/config', {
        method: 'PUT',
        body: JSON.stringify({ yaml_content: yaml }),
      });
      message.success('Configuration saved');
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Typography.Title level={3}>Settings</Typography.Title>
      <Typography.Paragraph type="secondary">
        Edit the global AxonFlow configuration. Changes take effect on next engine restart.
      </Typography.Paragraph>
      <YamlEditor value={yaml} onChange={setYaml} height="600px" />
      <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} style={{ marginTop: 12 }}>
        Save Configuration
      </Button>
    </>
  );
}
