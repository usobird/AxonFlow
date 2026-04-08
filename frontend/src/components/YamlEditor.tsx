import {} from 'react';
import Editor from '@monaco-editor/react';

interface Props {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
}

export default function YamlEditor({ value, onChange, readOnly = false, height = '400px' }: Props) {
  return (
    <Editor
      height={height}
      language="yaml"
      theme="vs-dark"
      value={value}
      onChange={(v) => onChange?.(v || '')}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
      }}
    />
  );
}
