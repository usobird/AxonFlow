import { useEffect, useState } from 'react';
import { Typography, Table, Button, Tag, Space, Spin } from 'antd';
import { PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { fetchApi } from '../api/client';

export default function Workflows() {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchApi('/api/workflows')
      .then(setWorkflows)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Workflows</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/workflows/new')}>
          New Workflow
        </Button>
      </Space>
      <Table
        dataSource={workflows}
        rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id' },
          { title: 'Name', dataIndex: 'name', key: 'name' },
          {
            title: 'Agents',
            dataIndex: 'agent_count',
            key: 'agents',
            render: (count: number) => count || 0,
          },
          {
            title: 'Trigger',
            key: 'trigger',
            render: (_: any, r: any) => <Tag>{r.trigger?.type || 'manual'}</Tag>,
          },
          {
            title: 'Actions',
            key: 'actions',
            render: (_: any, r: any) => (
              <Space>
                <Button type="primary" size="small" icon={<PlayCircleOutlined />}
                  onClick={() => navigate(`/workflows/${r.id}`)}>
                  Open
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}
