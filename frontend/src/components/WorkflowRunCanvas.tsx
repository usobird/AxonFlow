import { useMemo } from 'react';
import ReactFlow, { Background, Controls, MarkerType } from 'reactflow';
import type { Edge, Node } from 'reactflow';
import 'reactflow/dist/style.css';
import type { PlatformEdge, PlatformNode } from './WorkflowBuilder';

interface Props {
  nodes: PlatformNode[];
  edges: PlatformEdge[];
  nodeRuns: Array<{ node_id: string; status: string }>;
}

const colors: Record<string, { border: string; background: string; text: string }> = {
  queued: { border: '#91caff', background: '#e6f4ff', text: '#0050b3' },
  running: { border: '#ffe58f', background: '#fffbe6', text: '#ad6800' },
  completed: { border: '#b7eb8f', background: '#f6ffed', text: '#237804' },
  error: { border: '#ffccc7', background: '#fff2f0', text: '#cf1322' },
};

export default function WorkflowRunCanvas({ nodes, edges, nodeRuns }: Props) {
  const flowNodes = useMemo<Node[]>(() => {
    const statusByNode = new Map(nodeRuns.map((run) => [run.node_id, run.status]));
    return nodes.map((node) => {
      const status = statusByNode.get(node.id) || 'queued';
      const color = colors[status] || colors.queued;
      return {
        id: node.id,
        position: node.position,
        data: { label: `${node.label}\n${status}` },
        style: { width: 180, whiteSpace: 'pre-line', textAlign: 'center', border: `1px solid ${color.border}`, borderRadius: 6, background: color.background, color: color.text, fontWeight: 600 },
      };
    });
  }, [nodes, nodeRuns]);
  const flowEdges = useMemo<Edge[]>(() => edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.condition ? `${edge.condition.field} ${edge.condition.operator} ${String(edge.condition.value)}` : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  })), [edges]);

  return (
    <div style={{ height: 360, border: '1px solid #d9d9d9', background: '#fff' }}>
      <ReactFlow nodes={flowNodes} edges={flowEdges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
        <Background gap={18} size={1} color="#e8e8e8" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
