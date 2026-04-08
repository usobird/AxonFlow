import { useEffect, useState } from 'react';
import { Row, Col, Typography, Table, Tag, Spin } from 'antd';
import { RobotOutlined, ApartmentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import StatusCard from '../components/StatusCard';
import { fetchApi } from '../api/client';

interface SystemStatus {
  running: boolean;
  agents: Record<string, string>;
  tools: string[];
  token_usage: Record<string, any>;
}

export default function Dashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApi<SystemStatus>('/api/system/status')
      .then(setStatus)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const agentCount = status ? Object.keys(status.agents).length : 0;
  const toolCount = status?.tools?.length || 0;
  const totalTokens = status?.token_usage?.total_tokens || 0;

  const agentData = status
    ? Object.entries(status.agents).map(([id, state]) => ({ id, state }))
    : [];

  return (
    <>
      <Typography.Title level={3}>Dashboard</Typography.Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <StatusCard title="Active Agents" value={agentCount} color="#1890ff" icon={<RobotOutlined />} />
        </Col>
        <Col span={8}>
          <StatusCard title="Registered Tools" value={toolCount} color="#52c41a" icon={<ThunderboltOutlined />} />
        </Col>
        <Col span={8}>
          <StatusCard title="Tokens Used" value={totalTokens} color="#faad14" icon={<ApartmentOutlined />} />
        </Col>
      </Row>

      <Typography.Title level={5}>Agent Status</Typography.Title>
      <Table
        dataSource={agentData}
        rowKey="id"
        pagination={false}
        columns={[
          { title: 'Agent ID', dataIndex: 'id', key: 'id' },
          {
            title: 'State',
            dataIndex: 'state',
            key: 'state',
            render: (s: string) => (
              <Tag color={s === 'running' ? 'green' : s === 'working' ? 'blue' : s === 'error' ? 'red' : 'default'}>
                {s}
              </Tag>
            ),
          },
        ]}
      />
    </>
  );
}
