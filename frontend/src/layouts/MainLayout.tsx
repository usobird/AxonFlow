import {} from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined,
  ApartmentOutlined,
  RobotOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/workflows', icon: <ApartmentOutlined />, label: 'Workflows' },
  { key: '/agents', icon: <RobotOutlined />, label: 'Agents' },
  { key: '/logs', icon: <FileTextOutlined />, label: 'Logs' },
  { key: '/settings', icon: <SettingOutlined />, label: 'Settings' },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = menuItems.reduce((best, item) => {
    if (location.pathname.startsWith(item.key) && item.key.length > best.length) return item.key;
    return best;
  }, '/');

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark" style={{ position: 'fixed', left: 0, top: 0, bottom: 0 }}>
        <div style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>⚡</span>
          <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>AxonFlow</Typography.Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout style={{ marginLeft: 220 }}>
        <Content style={{ padding: 24, background: '#f0f2f5', minHeight: '100vh' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
