const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function harness(){
  const nodes=new Map(),calls=[],engines=[],timers=new Map();let clock=0,nextTimer=0;
  function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,attrs:{},listeners:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.listeners[k]=v;},replaceChildren(){},focus(){},querySelector(){return node('submit');}});return nodes.get(id);}
  const schedule=(fn,delay)=>{const id=++nextTimer;timers.set(id,{fn,at:clock+delay});return id;};
  function advance(ms){const target=clock+ms;while(true){const pending=[...timers].filter(([,v])=>v.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];if(!pending)break;clock=pending[1].at;timers.delete(pending[0]);pending[1].fn();}clock=target;}
  class Recognition{constructor(){engines.push(this);}start(){this.onstart();}abort(){this.onend();}}
  const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[]},window:{SpeechRecognition:Recognition,addEventListener(){}},AbortSignal,console:{...console,info(){}},setTimeout:schedule,clearTimeout:id=>timers.delete(id),fetch:async(url,options)=>{calls.push({url,options});if(url.endsWith('/me'))return {ok:false,status:401,json:async()=>({detail:'Entre'})};return {ok:true,json:async()=>({documents:[],message:'Nenhuma nota',count:0})};}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/assistant.js'),'utf8')+'\nthis.testApi={showEmployee};',context);
  await tick();context.testApi.showEmployee({profile:{re:'05',name:'Exemplo',role:'Funcionário',units:['Exemplo'],download:true,full_record:false},csrf_token:'demo'});
  const current=()=>engines.at(-1);
  const emitTo=(engine,...segments)=>engine.onresult({resultIndex:0,results:segments.map(([transcript,isFinal])=>Object.assign([{transcript}],{isFinal}))});
  const emit=(...segments)=>emitTo(current(),...segments);
  const queryCalls=()=>calls.filter(c=>c.url.endsWith('/query'));
  node('voice-start').onclick();
  return {node,calls,engines,current,emit,emitTo,advance,queryCalls};
}
test('eleven digits survive capture ending after the fourth digit and repeated pauses',async()=>{
  const h=await harness();assert.equal(h.current().continuous,true);assert.equal(h.current().interimResults,true);
  h.emit(['busque notas do CPF zero zero zero zero',true]);
  const first=h.current();first.onend();h.advance(250);assert.notEqual(h.current(),first);
  for(let i=0;i<6;i++){h.emit(['zero',true]);h.current().onerror({error:'no-speech'});h.current().onend();h.advance(250);}
  h.emit(['um',true]);assert.match(h.node('voice-status').textContent,/00000000001 · 11 dígitos/);
  assert.equal(h.queryCalls().length,0);
  h.emit(['um',true],['consulte',false]);assert.equal(h.queryCalls().length,0);
  h.emit(['um',true],['consulte',true]);await tick();
  assert.equal(h.queryCalls().length,1);
  const text=JSON.parse(h.queryCalls()[0].options.body).text;
  assert.equal((text.match(/zero/g)||[]).length,10);assert.equal((text.match(/um/g)||[]).length,1);
  assert.equal(h.node('submit').disabled,false);
});
test('interim revisions replace rather than duplicate the current engine hypothesis',async()=>{
  const h=await harness();h.emit(['nota 1',false]);h.emit(['nota 10',false]);h.emit(['nota 101',true]);
  assert.equal(h.node('employee-command').value,'nota 101');assert.equal(h.queryCalls().length,0);
  h.emit(['nota 101',true],['consulte',true]);await tick();assert.equal(h.queryCalls().length,1);
  assert.equal(JSON.parse(h.queryCalls()[0].options.body).text,'nota 101');
});
test('late events from an ended engine cannot overwrite a resumed transcription',async()=>{
  const h=await harness();h.emit(['nota zero zero',true]);const old=h.current();old.onend();h.advance(250);
  h.emit(['um',true]);h.emitTo(old,['nota 9 consulte',true]);old.onerror({error:'network'});old.onend();
  assert.equal(h.node('employee-command').value,'nota zero zero um');assert.equal(h.queryCalls().length,0);
  h.emit(['um',true],['consulte',true]);await tick();assert.equal(h.queryCalls().length,1);
});
test('stopping cancels scheduled restarts and ignores late confirmation',async()=>{
  const h=await harness();h.emit(['nota 101',true]);const old=h.current();old.onend();h.node('voice-stop').onclick();h.advance(1000);
  h.emitTo(old,['nota 101 consulte',true]);assert.equal(h.engines.length,1);assert.equal(h.queryCalls().length,0);
});
test('manual correction wins over late speech and sends once',async()=>{
  const h=await harness();h.emit(['nota 10',false]);const old=h.current();h.node('employee-command').value='nota 103';h.node('employee-command').listeners.input();
  h.emitTo(old,['nota 101 consulte',true]);assert.equal(h.node('employee-command').value,'nota 103');
  h.node('command-form').onsubmit({preventDefault(){}});h.node('command-form').onsubmit({preventDefault(){}});await tick();
  assert.equal(h.queryCalls().length,1);assert.equal(JSON.parse(h.queryCalls()[0].options.body).text,'nota 103');
});
test('network error preserves a draft for an explicit new capture',async()=>{
  const h=await harness();h.emit(['nota zero zero',true]);h.current().onerror({error:'network'});h.advance(1000);
  assert.equal(h.engines.length,1);assert.match(h.node('voice-status').textContent,/perdeu a conexão/);
  h.node('voice-start').onclick();h.emit(['um consulte',true]);await tick();
  assert.equal(JSON.parse(h.queryCalls()[0].options.body).text,'nota zero zero um');
});
test('permission failure does not restart or submit',async()=>{
  const h=await harness();h.current().onerror({error:'not-allowed'});h.advance(1000);
  assert.equal(h.engines.length,1);assert.equal(h.queryCalls().length,0);assert.match(h.node('voice-status').textContent,/não autorizado/);
});
test('idle timer bounds automatic listening and preserves the draft',async()=>{
  const h=await harness();h.emit(['nota zero',true]);h.current().onend();h.advance(90000);
  assert.equal(h.node('employee-command').value,'nota zero');assert.match(h.node('voice-status').textContent,/90 segundos/);
  const count=h.engines.length;h.current().onend();h.advance(1000);assert.equal(h.engines.length,count);assert.equal(h.queryCalls().length,0);
});
test('confirmation in a partial result never authorizes a lookup',async()=>{
  const h=await harness();h.emit(['nota 101 consulte',false]);await tick();assert.equal(h.queryCalls().length,0);
  h.emit(['nota 101 consulte',true]);h.emit(['nota 101 consulte',true]);await tick();assert.equal(h.queryCalls().length,1);
});
