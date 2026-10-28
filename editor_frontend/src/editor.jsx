import React, {useState, useCallback, useMemo, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, Handle, Position,
  BaseEdge, EdgeLabelRenderer, MarkerType, applyNodeChanges, useReactFlow} from '@xyflow/react';
import dagre from '@dagrejs/dagre';
import '@xyflow/react/dist/style.css';
import './style.css';

const colors = {CAUSES:'#d85f16', CHECKS:'#26806a', AFFECTS:'#af6e27', SUPPORTED_BY:'#888',
  CONNECTED_TO:'#555e68', HAS_COMPONENT:'#32363b', DEPENDS_ON:'#486ba4', CONTROLS:'#486ba4',
  PERFORMS:'#486ba4', MEASURES:'#486ba4', PRODUCES:'#486ba4', CONSUMES:'#486ba4', FLOWS_TO:'#486ba4'};

function StationNode({data, selected}) {
  return <div className={`station-node ${selected?'active':''}`} style={{borderLeftColor:data.color}}>
    <Handle type="target" position={data.horizontal?Position.Left:Position.Top}/>
    <span className="kind">{data.category}</span><strong>{data.label}</strong>
    <span className="node-id">{data.id}</span>
    {data.group && <small>In {data.group}</small>}
    <Handle type="source" position={data.horizontal?Position.Right:Position.Bottom}/>
  </div>;
}

// Parallel edges have independent IDs and visibly separate curves/labels.
function RelationEdge({id,sourceX,sourceY,targetX,targetY,data,markerEnd,style,selected}) {
  const offset=data.offset||0, mx=(sourceX+targetX)/2+offset, my=(sourceY+targetY)/2;
  const path=`M ${sourceX},${sourceY} Q ${mx+offset},${my} ${targetX},${targetY}`;
  return <><BaseEdge id={id} path={path} markerEnd={markerEnd} style={{...style,strokeWidth:selected?3:1.6}}/>
    <EdgeLabelRenderer><div className="relation-label nodrag nopan"
      style={{transform:`translate(-50%, -50%) translate(${mx}px,${my}px)`,borderColor:style.stroke}}
      title={data.description} onClick={e=>{e.stopPropagation();data.select(id);}}>{data.label}</div></EdgeLabelRenderer></>;
}
const nodeTypes={station:StationNode}, edgeTypes={relation:RelationEdge};

function layout(nodes,edges,direction) {
  const g=new dagre.graphlib.Graph({multigraph:true}).setDefaultEdgeLabel(()=>({}));
  g.setGraph({rankdir:direction,ranksep:100,nodesep:55,marginx:40,marginy:40});
  nodes.forEach(n=>g.setNode(n.id,{width:210,height:100}));
  edges.forEach(e=>g.setEdge(e.source,e.target,{},e.id));
  dagre.layout(g);
  return nodes.map(n=>({...n,position:{x:g.node(n.id).x-105,y:g.node(n.id).y-50}}));
}

function Canvas({data,emit}) {
  const rf=useReactFlow();
  const groupNames=Object.fromEntries(data.edges.filter(e=>e.type==='HAS_COMPONENT').map(e=>[e.target,data.nodes.find(n=>n.id===e.source)?.label]));
  const initial=useMemo(()=>{
    const nodes=data.nodes.map(n=>({id:n.id,type:'station',position:{x:0,y:0},
      selected:data.selected?.collection==='nodes'&&data.selected.id===n.id,
      data:{label:n.label,id:n.id,category:n.type,group:groupNames[n.id],horizontal:data.view==='causal',
        color:n.layer==='causal'?'#d85f16':n.layer==='diagnostic'?'#26806a':n.layer==='functional'?'#486ba4':'#555e68'}}));
    return layout(nodes,data.edges,data.view==='causal'?'LR':'TB').map(n=>({...n,
      position:data.layout?.positions?.[n.id]||n.position}));
  },[]);
  const [nodes,setNodes]=useState(initial);
  const nodesRef=useRef(nodes); nodesRef.current=nodes;
  const send=useCallback((action,extra={})=>emit({action,...extra,view:data.view,draft_id:data.draft_id,seq:data.seq,
    event_id:crypto.randomUUID(),positions:Object.fromEntries(nodesRef.current.map(n=>[n.id,n.position])),viewport:rf.getViewport()}),[data,rf,emit]);
  const edges=useMemo(()=>{
    const groups={}; data.edges.forEach(e=>{const k=[e.source,e.target].sort().join('|');(groups[k]??=[]).push(e);});
    return data.edges.map(e=>{const peers=groups[[e.source,e.target].sort().join('|')];
      return {id:e.id,source:e.source,target:e.target,type:'relation',selected:data.selected?.id===e.id,
        reconnectable:data.edit,markerEnd:{type:MarkerType.ArrowClosed,color:colors[e.type]||'#888'},
        style:{stroke:colors[e.type]||'#888',strokeDasharray:e.type==='DEPENDS_ON'?'6 4':undefined},
        data:{label:e.type,description:e.description||e.condition||e.id,
          offset:(peers.indexOf(e)-(peers.length-1)/2)*55,select:id=>send('select',{collection:'edges',id})}};
    });
  },[data,send]);
  const reset=()=>{const arranged=layout(nodes,data.edges,data.view==='causal'?'LR':'TB');setNodes(arranged);
    nodesRef.current=arranged;requestAnimationFrame(()=>rf.fitView({padding:.2}));};
  return <div className="editor-canvas">
    <div className="canvas-toolbar"><div><b>{data.nodes.length}</b> nodes · <b>{data.edges.length}</b> relationships</div>
      <div className="toolbar-buttons">
        <button disabled={!data.edit} onClick={()=>send('create_node')}>＋ Node</button>
        <button disabled={!data.edit} onClick={()=>send('create_edge')}>＋ Relationship</button>
        <button disabled={!data.edit} onClick={()=>send('create_fault')}>＋ Fault mode</button>
        <button onClick={reset}>Reset layout</button>
        <button onClick={()=>send('save_layout')}>Save layout</button>
      </div></div>
    <div className="flow-area">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
        onNodesChange={changes=>setNodes(old=>applyNodeChanges(changes.filter(c=>c.type!=='remove'),old))}
        onNodeClick={(_,node)=>send('select',{collection:'nodes',id:node.id})}
        onEdgeClick={(_,edge)=>send('select',{collection:'edges',id:edge.id})}
        onNodeDragStop={(_,node)=>{nodesRef.current=nodesRef.current.map(n=>n.id===node.id?node:n);send('layout_changed');}}
        onConnect={connection=>send('connect',connection)}
        onReconnect={(edge,connection)=>send('reconnect',{id:edge.id,...connection})}
        nodesConnectable={data.edit} edgesReconnectable={data.edit} deleteKeyCode={null}
        minZoom={.05} maxZoom={2.5} fitView={!data.layout?.viewport} defaultViewport={data.layout?.viewport||{x:0,y:0,zoom:1}}
        fitViewOptions={{padding:.2}} onlyRenderVisibleElements ariaLabelConfig={{'controls.fitView.ariaLabel':'Fit graph to view'}}>
        <Background gap={22} color="#ddd8d0"/><Controls showInteractive={false}/><MiniMap pannable zoomable style={{width:120,height:85}} nodeColor={n=>n.data.color}/>
      </ReactFlow>
    </div>
    <div className="canvas-legend"><span>— Physical</span><span style={{color:'#486ba4'}}>┄ Dependency / function</span>
      <span style={{color:'#d85f16'}}>→ Conditional cause</span><span style={{color:'#26806a'}}>→ Diagnostic check</span></div>
    <div className="canvas-hint">Drag to arrange · scroll to zoom · connect output handles (bottom/right) to input handles (top/left) · select to inspect</div>
  </div>;
}

export default function render({parentElement,data,setTriggerValue}) {
  // Streamlit can render new data before the preceding cleanup is invoked.
  // Dispose our own root explicitly so an obsolete, clipped canvas cannot emit stale edits.
  parentElement.querySelectorAll('[data-station-react-root]').forEach(host=>host.__stationDispose?.());
  const host=document.createElement('div');host.dataset.stationReactRoot='';parentElement.appendChild(host);
  const root=createRoot(host);
  root.render(<ReactFlowProvider><Canvas data={data} emit={event=>setTriggerValue('action',event)}/></ReactFlowProvider>);
  let disposed=false;
  host.__stationDispose=()=>{if(!disposed){disposed=true;root.unmount();host.remove();}};
  return host.__stationDispose;
}
