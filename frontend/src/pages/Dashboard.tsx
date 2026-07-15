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

const agentStatePresentation: Record<string, { label: string; color: string }> = {
  idle: { label: 'Idle', color: 'default' },
  running: { label: 'Ready', color: 'green' },
  working: { label: 'Working', color: 'blue' },
  error: { label: 'Error', color: 'red' },
  stopped: { label: 'Stopped', color: 'default' },
};

export default function Dashboard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const loadStatus = async () => {
      try {
        const nextStatus = await fetchApi<SystemStatus>('/api/system/status');
        if (mounted) setStatus(nextStatus);
      } catch (error) {
        console.error(error);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void loadStatus();
    const intervalId = window.setInterval(() => { void loadStatus(); }, 2000);
    return () => {
      mounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const agentStates = Object.values(status?.agents || {});
  const registeredAgentCount = agentStates.length;
  const workingAgentCount = agentStates.filter((state) => state === 'working').length;
  const readyAgentCount = agentStates.filter((state) => state === 'running').length;
  const toolCount = status?.tools?.length || 0;
  const totalTokens = status?.token_usage?.total_tokens || 0;

  const agentData = status
    ? Object.entries(status.agents).map(([id, state]) => ({ id, state }))
    : [];

  return (
    <>
      <Typography.Title level={3}>Dashboard</Typography.Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard title="Working Agents" value={workingAgentCount} color="#1677ff" icon={<RobotOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard title="Ready Agents" value={readyAgentCount} color="#52c41a" icon={<RobotOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard title="Registered Tools" value={toolCount} color="#52c41a" icon={<ThunderboltOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard title="Tokens Used" value={totalTokens} color="#faad14" icon={<ApartmentOutlined />} />
        </Col>
      </Row>

      <Typography.Title level={5}>Agent Activity ({registeredAgentCount} registered)</Typography.Title>
      <Table
        dataSource={agentData}
        rowKey="id"
        pagination={false}
        columns={[
          { title: 'Agent ID', dataIndex: 'id', key: 'id' },
          {
            title: 'Activity',
            dataIndex: 'state',
            key: 'state',
            render: (state: string) => {
              const presentation = agentStatePresentation[state] || agentStatePresentation.idle;
              return <Tag color={presentation.color}>{presentation.label}</Tag>;
            },
          },
        ]}
      />
    </>
  );
}
