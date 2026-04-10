import React from 'react';
import { Card, Statistic } from 'antd';

interface Props {
  title: string;
  value: number | string;
  color?: string;
  icon?: React.ReactNode;
}

export default function StatusCard({ title, value, color, icon }: Props) {
  return (
    <Card>
      <Statistic title={title} value={value} valueStyle={{ color }} prefix={icon} />
    </Card>
  );
}
