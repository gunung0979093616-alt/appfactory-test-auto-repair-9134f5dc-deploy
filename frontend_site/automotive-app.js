async function callTool(name,args={}){const response=await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json','MCP-Protocol-Version':'2026-07-28'},body:JSON.stringify({jsonrpc:'2.0',id:Date.now(),method:'tools/call',params:{name,arguments:args}})});const payload=await response.json();if(payload.error)throw new Error(payload.error.message||'工具呼叫失敗');return JSON.parse(payload.result.content[0].text)}
function operationKey(prefix){return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`}
function formatJson(value){return JSON.stringify(value,null,2)}
window.AutomotiveApp={callTool,operationKey,formatJson};
