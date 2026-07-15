import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Empty, Input, Select, Typography } from 'antd';
import ReactFlow, {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
} from 'reactflow';
import type { Connection, Edge, EdgeChange, Node, NodeChange, NodeProps } from 'reactflow';
import 'reactflow/dist/style.css';

export interface AgentManifest {
  id: string;
  name: string;
  description: string;
  tags: string[];
  tools: string[];
  model?: string;
}

export interface PlatformNode {
  id: string;
  agent_id: string;
  label: string;
  position: { x: number; y: number };
  is_entry: boolean;
  config: Record<string, unknown>;
}

export interface PlatformEdge {
  id: string;
  source: string;
  target: string;
  condition?: { field: string; operator: string; value: unknown } | null;
}

interface AgentNodeData {
  label: string;
  agentId: string;
  isEntry: boolean;
  responsibility: string;
  terminateOnSuccess: boolean;
}

const connectorStyle = {
  width: 24,
  height: 24,
  background: '#1677ff',
  border: '3px solid #fff',
  borderRadius: '50%',
  boxShadow: '0 1px 5px rgba(0, 80, 179, 0.45)',
  cursor: 'crosshair',
  zIndex: 2,
};

function AgentNode({ data }: NodeProps<AgentNodeData>) {
  return (
    <div style={{ minWidth: 170, border: '1px solid #91caff', borderRadius: 6, background: '#fff', overflow: 'visible' }}>
      <Handle
        id="input"
        type="target"
        position={Position.Left}
        title="Drag a connection into this Agent"
        style={{ ...connectorStyle, left: -12 }}
      />
      <div style={{ padding: '8px 10px', background: '#e6f4ff', color: '#0050b3', fontWeight: 600, fontSize: 13 }}>
        {data.label}
      </div>
      <div style={{ padding: '7px 10px', color: '#595959', fontSize: 12 }}>
        {data.agentId}
        {data.isEntry && <span style={{ marginLeft: 8, color: '#389e0d' }}>Entry</span>}
        {data.terminateOnSuccess && <span style={{ marginLeft: 8, color: '#d46b08' }}>End</span>}
      </div>
      {data.responsibility && (
        <div style={{ padding: '0 10px 8px', color: '#595959', fontSize: 12, lineHeight: 1.45 }}>
          {data.responsibility.length > 84 ? `${data.responsibility.slice(0, 84)}...` : data.responsibility}
        </div>
      )}
      <Handle
        id="output"
        type="source"
        position={Position.Right}
        title="Drag from here to the next Agent"
        style={{ ...connectorStyle, right: -12 }}
      />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

function toFlowNodes(nodes: PlatformNode[], agents: AgentManifest[] = []): Node<AgentNodeData>[] {
  return nodes.map((node) => ({
    id: node.id,
    type: 'agent',
    position: node.position,
    data: {
      label: node.label === node.agent_id
        ? agents.find((agent) => agent.id === node.agent_id)?.name || node.label
        : node.label,
      agentId: node.agent_id,
      isEntry: node.is_entry,
      responsibility: typeof node.config?.responsibility === 'string' ? node.config.responsibility : '',
      terminateOnSuccess: node.config?.terminate_on_success === true,
    },
  }));
}

function toFlowEdges(edges: PlatformEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: { condition: edge.condition || null },
    label: edge.condition ? `${edge.condition.field} ${edge.condition.operator} ${String(edge.condition.value)}` : undefined,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
}

function toPlatformNodes(nodes: Node<AgentNodeData>[]): PlatformNode[] {
  return nodes.map((node) => ({
    id: node.id,
    agent_id: node.data.agentId,
    label: node.data.label,
    position: node.position,
    is_entry: node.data.isEntry,
    config: {
      ...(node.data.responsibility.trim() ? { responsibility: node.data.responsibility.trim() } : {}),
      terminate_on_success: node.data.terminateOnSuccess,
    },
  }));
}

function toPlatformEdges(edges: Edge[]): PlatformEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    condition: (edge.data?.condition as PlatformEdge['condition']) || null,
  }));
}

interface Props {
  initialNodes: PlatformNode[];
  initialEdges: PlatformEdge[];
  agents: AgentManifest[];
}

export interface WorkflowBuilderHandle {
  getGraph: () => { nodes: PlatformNode[]; edges: PlatformEdge[] };
}

const WorkflowBuilder = forwardRef<WorkflowBuilderHandle, Props>(function WorkflowBuilder(
  { initialNodes, initialEdges, agents },
  ref,
) {
  const [nodes, setNodes] = useState<Node<AgentNodeData>[]>(() => toFlowNodes(initialNodes, agents));
  const [edges, setEdges] = useState<Edge[]>(() => toFlowEdges(initialEdges));
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setNodes(toFlowNodes(initialNodes, agents));
    setEdges(toFlowEdges(initialEdges));
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  // The editor is remounted for each workflow route; do not reset on every drag.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialNodes.length === 0 ? '' : initialNodes[0].id]);

  useImperativeHandle(ref, () => ({
    getGraph: () => ({ nodes: toPlatformNodes(nodes), edges: toPlatformEdges(edges) }),
  }), [nodes, edges]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((current) => {
      const next = applyNodeChanges(changes, current) as Node<AgentNodeData>[];
      return next;
    });
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((current) => {
      const next = applyEdgeChanges(changes, current);
      return next;
    });
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    setEdges((current) => {
      const next = addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, current);
      return next;
    });
    setNodes((current) => current.map((node) => {
      if (node.id === connection.source) {
        return { ...node, data: { ...node.data, terminateOnSuccess: false } };
      }
      if (node.id === connection.target && !edges.some((edge) => edge.source === node.id)) {
        return { ...node, data: { ...node.data, terminateOnSuccess: true } };
      }
      return node;
    }));
  }, [edges]);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );
  const selectedEdge = useMemo(
    () => edges.find((edge) => edge.id === selectedEdgeId) || null,
    [edges, selectedEdgeId],
  );

  const updateNode = (patch: Partial<AgentNodeData>) => {
    if (!selectedNode) return;
    setNodes((current) => {
      const next = current.map((node) => {
        if (node.id !== selectedNode.id) return node;
        if (patch.isEntry) {
          return { ...node, data: { ...node.data, ...patch, isEntry: true } };
        }
        return { ...node, data: { ...node.data, ...patch } };
      }).map((node) => (
        patch.isEntry && node.id !== selectedNode.id
          ? { ...node, data: { ...node.data, isEntry: false } }
          : node
      ));
      return next;
    });
  };

  const updateEdgeCondition = (value: string) => {
    if (!selectedEdge) return;
    setEdges((current) => {
      const condition = value.trim()
        ? { field: 'status', operator: 'eq', value: value.trim() }
        : null;
      const next = current.map((edge) => edge.id === selectedEdge.id ? {
        ...edge,
        data: { ...edge.data, condition },
        label: condition ? `status eq ${value.trim()}` : undefined,
      } : edge);
      return next;
    });
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const agentId = event.dataTransfer.getData('application/axonflow-agent');
    const agent = agents.find((item) => item.id === agentId);
    const bounds = canvasRef.current?.getBoundingClientRect();
    if (!agent || !bounds || nodes.some((node) => node.data.agentId === agent.id)) return;
    const id = `node-${agent.id}`;
    const nextNode: Node<AgentNodeData> = {
      id,
      type: 'agent',
      position: { x: event.clientX - bounds.left - 85, y: event.clientY - bounds.top - 35 },
      data: {
        label: agent.name,
        agentId: agent.id,
        isEntry: nodes.length === 0,
        responsibility: '',
        terminateOnSuccess: true,
      },
    };
    const next = [...nodes, nextNode];
    setNodes(next);
  };

  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    setNodes((current) => {
      const remaining = current.filter((node) => node.id !== selectedNode.id);
      if (selectedNode.data.isEntry && remaining.length) {
        return remaining.map((node, index) => ({
          ...node,
          data: { ...node.data, isEntry: index === 0 },
        }));
      }
      return remaining;
    });
    setEdges((current) => current.filter((edge) => (
      edge.source !== selectedNode.id && edge.target !== selectedNode.id
    )));
    setSelectedNodeId(null);
  };

  const deleteSelectedEdge = () => {
    if (!selectedEdge) return;
    setEdges((current) => current.filter((edge) => edge.id !== selectedEdge.id));
    setSelectedEdgeId(null);
  };

  return (
    <div style={{ overflowX: 'auto', border: '1px solid #d9d9d9', background: '#fff' }}>
      <div style={{ height: 640, minWidth: 720, display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr) 260px' }}>
      <aside style={{ borderRight: '1px solid #f0f0f0', padding: 14, overflowY: 'auto' }}>
        <Typography.Text strong>Agent Library</Typography.Text>
        <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
          {agents.map((agent) => (
            <div
              key={agent.id}
              draggable
              onDragStart={(event) => {
                event.dataTransfer.setData('application/axonflow-agent', agent.id);
                event.dataTransfer.effectAllowed = 'move';
              }}
              title={agent.description}
              style={{ padding: '9px 10px', border: '1px solid #d9d9d9', borderRadius: 4, cursor: 'grab', background: '#fafafa' }}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>{agent.name}</div>
              <div style={{ color: '#8c8c8c', fontSize: 11, marginTop: 2 }}>{agent.id}</div>
            </div>
          ))}
        </div>
      </aside>
      <div
        ref={canvasRef}
        onDrop={onDrop}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'move';
        }}
        style={{ minWidth: 0 }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => { setSelectedNodeId(node.id); setSelectedEdgeId(null); }}
          onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(null); }}
          onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
          fitView
        >
          <Background gap={18} size={1} color="#e8e8e8" />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>
      <aside style={{ borderLeft: '1px solid #f0f0f0', padding: 14, overflowY: 'auto' }}>
        {selectedNode && (
          <div style={{ display: 'grid', gap: 12 }}>
            <Typography.Text strong>Node Settings</Typography.Text>
            <div>
              <Typography.Text type="secondary">Agent</Typography.Text>
              <Select
                style={{ width: '100%', marginTop: 4 }}
                value={selectedNode.data.agentId}
                options={agents
                  .filter((agent) => agent.id === selectedNode.data.agentId || !nodes.some((node) => node.data.agentId === agent.id))
                  .map((agent) => ({ value: agent.id, label: agent.name }))}
                onChange={(agentId) => {
                  const agent = agents.find((item) => item.id === agentId);
                  updateNode({ agentId, label: agent?.name || agentId });
                }}
              />
            </div>
            <div>
              <Typography.Text type="secondary">Label</Typography.Text>
              <Input value={selectedNode.data.label} onChange={(event) => updateNode({ label: event.target.value })} style={{ marginTop: 4 }} />
            </div>
            <div>
              <Typography.Text type="secondary">Workflow responsibility</Typography.Text>
              <Input.TextArea
                rows={5}
                value={selectedNode.data.responsibility}
                placeholder="Describe this Agent's responsibility in this workflow"
                onChange={(event) => updateNode({ responsibility: event.target.value })}
                style={{ marginTop: 4 }}
              />
            </div>
            <Checkbox checked={selectedNode.data.isEntry} onChange={(event) => event.target.checked && updateNode({ isEntry: true })}>
              Entry node
            </Checkbox>
            <Checkbox
              checked={selectedNode.data.terminateOnSuccess}
              onChange={(event) => updateNode({ terminateOnSuccess: event.target.checked })}
            >
              Complete workflow when this Agent succeeds
            </Checkbox>
            <Button danger onClick={deleteSelectedNode}>Remove node</Button>
          </div>
        )}
        {selectedEdge && (
          <div style={{ display: 'grid', gap: 12 }}>
            <Typography.Text strong>Route Condition</Typography.Text>
            <Typography.Text type="secondary">Run only when the upstream status matches this value.</Typography.Text>
            <Input
              placeholder="Leave empty for default route"
              value={String((selectedEdge.data?.condition as PlatformEdge['condition'])?.value || '')}
              onChange={(event) => updateEdgeCondition(event.target.value)}
            />
            <Button danger onClick={deleteSelectedEdge}>Remove route</Button>
          </div>
        )}
        {!selectedNode && !selectedEdge && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Select a node or route" />}
      </aside>
      </div>
    </div>
  );
});

export default WorkflowBuilder;
