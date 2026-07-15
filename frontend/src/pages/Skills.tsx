import { useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Popconfirm, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { fetchApi } from '../api/client';

interface Skill {
  id: string;
  content: string;
  has_scripts: boolean;
}

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Skill | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<Skill>();

  const load = async () => {
    const result = await fetchApi<Skill[]>('/api/skills');
    setSkills(result);
  };

  useEffect(() => {
    load().catch((error: Error) => message.error(error.message)).finally(() => setLoading(false));
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({ id: '', content: '# New Skill\n\nDescribe the reusable procedure.' });
    setModalOpen(true);
  };

  const openEdit = (skill: Skill) => {
    setEditing(skill);
    form.setFieldsValue(skill);
    setModalOpen(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    const path = `/api/skills/${editing?.id || values.id}`;
    await fetchApi(path, {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify({ content: values.content }),
    });
    setModalOpen(false);
    await load();
    message.success(editing ? 'Skill saved' : 'Skill created');
  };

  const remove = async (skill: Skill) => {
    await fetchApi(`/api/skills/${skill.id}`, { method: 'DELETE' });
    await load();
    message.success('Skill deleted');
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Skills</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>New Skill</Button>
      </Space>
      <Table<Skill>
        dataSource={skills}
        rowKey="id"
        pagination={false}
        columns={[
          { title: 'ID', dataIndex: 'id' },
          { title: 'Content', dataIndex: 'content', render: (content: string) => content.replace(/\s+/g, ' ').slice(0, 140) },
          { title: 'Assets', render: (_, skill) => skill.has_scripts ? <Tag color="blue">scripts</Tag> : '-' },
          {
            title: '',
            key: 'actions',
            width: 110,
            render: (_, skill) => <Space size={0}>
              <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(skill)} aria-label={`Edit ${skill.id}`} />
              <Popconfirm title="Delete this Skill?" onConfirm={() => remove(skill)}>
                <Button danger type="text" icon={<DeleteOutlined />} aria-label={`Delete ${skill.id}`} />
              </Popconfirm>
            </Space>,
          },
        ]}
      />
      <Modal title={editing ? `Edit ${editing.id}` : 'New Skill'} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={save} okText="Save">
        <Form form={form} layout="vertical">
          <Form.Item name="id" label="Skill ID" rules={editing ? [] : [{ required: true }, { pattern: /^[a-z][a-z0-9-]{2,63}$/ }]}>
            <Input disabled={Boolean(editing)} placeholder="release-checklist" />
          </Form.Item>
          <Form.Item name="content" label="SKILL.md" rules={[{ required: true }]}>
            <Input.TextArea rows={16} spellCheck={false} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
