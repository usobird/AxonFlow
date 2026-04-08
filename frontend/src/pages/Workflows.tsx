import { useEffect, useState } from 'react';
import { Typography, Table, Button, Tag, Space, Spin } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
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
      <Typography.Title level={3}>Workflows</Typography.Title>
      <Table
        dataSource={workflows}
        rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id' },
          { title: 'Name', dataIndex: 'name', key: 'name' },
          {
            title: 'Agents',
            dataIndex: 'agents',
            key: 'agents',
            render: (agents: string[]) => agents?.length || 0,
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
                  Detail
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}
