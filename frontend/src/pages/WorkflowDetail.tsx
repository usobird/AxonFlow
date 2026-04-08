import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Tabs, Button, message, Input, Modal, Spin, Table, Tag } from 'antd';
import { PlayCircleOutlined, SaveOutlined } from '@ant-design/icons';
import YamlEditor from '../components/YamlEditor';
import { fetchApi } from '../api/client';

export default function WorkflowDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<any>(null);
  const [yaml, setYaml] = useState('');
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [runInput, setRunInput] = useState('Hello');

  useEffect(() => {
    if (!id) return;
    Promise.all([
      fetchApi(`/api/workflows/${id}`),
      fetchApi(`/api/workflows/${id}/runs`),
    ])
      .then(([wf, rs]) => {
        setWorkflow(wf);
        setYaml(JSON.stringify(wf, null, 2));
        setRuns(rs);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    try {
      await fetchApi(`/api/workflows/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ yaml_content: yaml }),
      });
      message.success('Workflow saved');
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const handleRun = async () => {
    try {
      const res = await fetchApi(`/api/workflows/${id}/run`, {
        method: 'POST',
        body: JSON.stringify({ input: runInput }),
      });
      setRunModalOpen(false);
      message.success(`Workflow started: ${res.run_id}`);
      navigate(`/workflows/${id}/runs/${res.run_id}`);
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Workflow: {workflow?.name || id}
        </Typography.Title>
        <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRunModalOpen(true)}>
          Run
        </Button>
      </div>

      <Tabs items={[
        {
          key: 'config',
          label: 'Configuration',
          children: (
            <>
              <YamlEditor value={yaml} onChange={setYaml} height="500px" />
              <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} style={{ marginTop: 12 }}>
                Save
              </Button>
            </>
          ),
        },
        {
          key: 'runs',
          label: 'Run History',
          children: (
            <Table
              dataSource={runs}
              rowKey="run_id"
              pagination={false}
              columns={[
                { title: 'Run ID', dataIndex: 'run_id', key: 'run_id' },
                {
                  title: 'Status',
                  dataIndex: 'status',
                  key: 'status',
                  render: (s: string) => <Tag color={s === 'completed' ? 'green' : s === 'error' ? 'red' : 'blue'}>{s}</Tag>,
                },
                { title: 'Iterations', dataIndex: 'iterations', key: 'iterations' },
                { title: 'Duration (s)', dataIndex: 'duration_seconds', key: 'duration' },
                {
                  title: 'Actions',
                  key: 'actions',
                  render: (_: any, r: any) => (
                    <Button size="small" onClick={() => navigate(`/workflows/${id}/runs/${r.run_id}`)}>
                      View
                    </Button>
                  ),
                },
              ]}
            />
          ),
        },
      ]} />

      <Modal
        title="Run Workflow"
        open={runModalOpen}
        onOk={handleRun}
        onCancel={() => setRunModalOpen(false)}
      >
        <Typography.Text>Input:</Typography.Text>
        <Input.TextArea
          value={runInput}
          onChange={(e) => setRunInput(e.target.value)}
          rows={4}
          style={{ marginTop: 8 }}
        />
      </Modal>
    </>
  );
}
