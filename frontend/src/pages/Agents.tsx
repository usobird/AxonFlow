import { useEffect, useState } from 'react';
import { Typography, Table, Button, Tag, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { fetchApi } from '../api/client';

export default function Agents() {
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchApi('/api/agents')
      .then(setAgents)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Typography.Title level={3}>Agents</Typography.Title>
      <Table
        dataSource={agents}
        rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id' },
          { title: 'Name', dataIndex: 'name', key: 'name' },
          { title: 'Role', dataIndex: 'role', key: 'role' },
          {
            title: 'Model',
            key: 'model',
            render: (_: any, r: any) => <Tag>{r.model?.name || 'default'}</Tag>,
          },
          {
            title: 'Tools',
            key: 'tools',
            render: (_: any, r: any) => r.tools?.length || 0,
          },
          {
            title: 'Actions',
            key: 'actions',
            render: (_: any, r: any) => (
              <Button size="small" onClick={() => navigate(`/agents/${r.id}`)}>
                Detail
              </Button>
            ),
          },
        ]}
      />
    </>
  );
}
