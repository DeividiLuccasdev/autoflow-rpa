const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function harness(){
  const nodes=new Map(), calls=[];
  function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,attrs:{},listeners:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.listeners[k]=v;},replaceChildren(){},focus(){},querySelector(){return node('submit');}});return nodes.get(id);}
  class Recognition{start(){this.onstart();}stop(){this.onend();}abort(){this.onend();}}
  const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[]},window:{SpeechRecognition:Recognition,addEventListener(){}},AbortSignal,console,setTimeout,clearTimeout,fetch:async(url,options)=>{calls.push({url,options});if(url.endsWith('/me'))return {ok:false,status:401,json:async()=>({detail:'Entre'})};return {ok:true,json:async()=>({documents:[],message:'Nenhuma nota',count:0})};}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/assistant.js'),'utf8')+'\nthis.testApi={showEmployee,getRecognition:()=>recognition};',context);
  await tick();context.testApi.showEmployee({profile:{re:'05',name:'Exemplo',role:'Funcionário',units:['Exemplo'],download:true,full_record:false},csrf_token:'demo'});
  const speech=context.testApi.getRecognition();
  const emit=(...segments)=>speech.onresult({results:segments.map(([transcript,isFinal])=>Object.assign([{transcript}],{isFinal}))});
  node('voice-start').onclick();
  return {node,calls,speech,emit};
}
test('partial speech updates immediately; revised partials do not duplicate or query',async()=>{
  const h=await harness();assert.equal(h.speech.interimResults,true);
  h.emit(['nota',false]);assert.equal(h.node('employee-command').value,'nota');
  h.emit(['nota 10',false]);assert.equal(h.node('employee-command').value,'nota 10');
  h.emit(['nota 101',false]);assert.equal(h.node('employee-command').value,'nota 101');
  assert.equal(h.calls.filter(c=>c.url.endsWith('/query')).length,0);
  h.emit(['nota 101',true]);
  assert.equal(h.node('submit').disabled,true);
  assert.equal(h.node('employee-message').textContent,'Consultando…');
  h.emit(['nota 101',true]);await tick();
  const queries=h.calls.filter(c=>c.url.endsWith('/query'));assert.equal(queries.length,1);
  assert.equal(JSON.parse(queries[0].options.body).text,'nota 101');
  assert.equal(h.node('submit').disabled,false);
});
test('multiple segments preserve final text and updated interim numbers',async()=>{
  const h=await harness();h.emit(['notas CPF',true],['zero zero',false]);
  assert.equal(h.node('employee-command').value,'notas CPF zero zero');
  assert.equal(h.calls.filter(c=>c.url.endsWith('/query')).length,0);
  h.emit(['notas CPF',true],['00000000001',true]);await tick();
  assert.equal(JSON.parse(h.calls.find(c=>c.url.endsWith('/query')).options.body).text,'notas CPF 00000000001');
});
test('manual editing cancels pending speech and preserves correction',async()=>{
  const h=await harness();h.emit(['nota 10',false]);h.node('employee-command').value='nota 103';h.node('employee-command').listeners.input();
  h.emit(['nota 101',true]);assert.equal(h.node('employee-command').value,'nota 103');
  assert.equal(h.calls.filter(c=>c.url.endsWith('/query')).length,0);
  h.node('command-form').onsubmit({preventDefault(){}});await tick();
  assert.equal(JSON.parse(h.calls.find(c=>c.url.endsWith('/query')).options.body).text,'nota 103');
});
test('manual submit during dictation sends once; ending partial speech never auto queries',async()=>{
  const h=await harness();h.emit(['nota 101',false]);h.node('command-form').onsubmit({preventDefault(){}});h.emit(['nota 101',true]);await tick();
  assert.equal(h.calls.filter(c=>c.url.endsWith('/query')).length,1);
  const partial=await harness();partial.emit(['CPF 000',false]);partial.speech.onend();await tick();
  assert.equal(partial.calls.filter(c=>c.url.endsWith('/query')).length,0);
});
