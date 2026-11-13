const byId=id=>document.getElementById(id);
const safe=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money=value=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let employee=null, employeeCsrf='', employeeResults=[], openedDocument=null, recognition=null, listening=false, commandBusy=false;
let collectionBusy=false;
let voiceActive=false, voiceCancelled=false, voiceSubmitted=false;
let voiceEpoch=0, voiceRestartTimer=null, voiceIdleTimer=null, voicePrefix='', voiceResume=false;
function voiceEvent(event,detail={}){
  // Diagnóstico local, sem áudio, texto transcrito ou identificadores.
  console.info('[AutoFlow voz]',{event,session:voiceEpoch,...detail});
}

function cancelVoiceInput(){
  if(voiceActive)voiceEvent('cancel');
  voiceCancelled=true;voiceActive=false;voiceResume=false;voiceEpoch++;
  clearTimeout(voiceRestartTimer);clearTimeout(voiceIdleTimer);
  const previous=recognition;recognition=null;
  listening=false;byId('voice-start').setAttribute('aria-pressed','false');byId('voice-stop').hidden=true;
  previous?.abort();
}

async function employeeRequest(path,method='GET',body){
  const response=await fetch('/assistant'+path,{method,headers:{...(method==='POST'?{'X-Voice-CSRF':employeeCsrf}:{}),...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(90000)});
  if(!response.ok){const data=await response.json();if(response.status===401)clearEmployee();throw new Error(typeof data.detail==='string'?data.detail:'Confira os campos informados.');}
  return response;
}
function clearEmployee(){
  cancelVoiceInput();employee=null;employeeCsrf='';employeeResults=[];openedDocument=null;
  byId('assistant-panel').hidden=true;byId('login-panel').hidden=false;byId('document-detail').hidden=true;byId('employee-history').hidden=true;
  byId('document-results').replaceChildren();byId('document-fields').replaceChildren();byId('document-items').replaceChildren();byId('employee-events').replaceChildren();byId('assistant-answer').textContent='';byId('employee-command').value='';
  byId('collection-preview').hidden=true;byId('collection-history').replaceChildren();byId('collection-message').textContent='';
}
function showEmployee(data){
  employee=data.profile;employeeCsrf=data.csrf_token;byId('login-panel').hidden=true;byId('assistant-panel').hidden=false;
  byId('employee-name').textContent=`R.E. ${employee.re} · ${employee.role}`;
  byId('employee-access').textContent=`${employee.name} · Unidades: ${employee.units.join(' e ')} · ${employee.download?'Download autorizado':'Sem download de PDF'} · ${employee.full_record?'Ficha completa de cobrança':'Nota, valor devedor e razão social'}`;
  byId('employee-message').textContent='';setupRecognition();loadCollections().catch(()=>{});
}
byId('employee-login').onsubmit=async event=>{
  event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;byId('employee-message').textContent='Autenticando R.E.…';
  try{const response=await employeeRequest('/login','POST',{re:byId('employee-re').value.trim(),password:byId('employee-password').value});showEmployee(await response.json());byId('employee-command').focus();}
  catch(error){byId('employee-message').textContent=error.message;}
  finally{button.disabled=false;byId('employee-password').value='';}
};
async function employeeLogout(){
  try{await employeeRequest('/logout','POST');clearEmployee();byId('employee-message').textContent='Sessão encerrada.';}
  catch(error){byId('employee-message').textContent=error.message;}
}
byId('employee-logout').onclick=employeeLogout;

async function openEmployeeDocument(id){
  const response=await employeeRequest('/documents/'+encodeURIComponent(id));openedDocument=await response.json();
  byId('document-detail').hidden=false;byId('employee-history').hidden=true;byId('document-title').textContent='Nota '+openedDocument.number;
  byId('download-pdf').hidden=!openedDocument.can_download;
  byId('generate-collection').hidden=!openedDocument.can_download;
  byId('collection-preview').hidden=true;byId('collection-message').textContent='';
  const fields=[['Número',openedDocument.number],['Unidade',openedDocument.unit],['Data',openedDocument.date],['Razão social fictícia',openedDocument.debtor_name],[openedDocument.tax_type,openedDocument.tax_id],['Valor da nota',money(openedDocument.amount)],['Valor devedor da nota',money(openedDocument.outstanding_amount)],['Situação',openedDocument.status]];
  if(employee.full_record)fields.push(['Endereço fictício',openedDocument.address],['Telefone fictício',openedDocument.phone],['Valor total da dívida',money(openedDocument.total_debt)],['Parcelas restantes',openedDocument.remaining_installments]);
  byId('document-fields').innerHTML=fields.map(([label,value])=>`<div><dt>${safe(label)}</dt><dd>${safe(value)}</dd></div>`).join('');
  byId('document-items').innerHTML=openedDocument.items.map(item=>`<article class="line-item"><strong>${safe(item.description)}</strong><span>${item.quantity} unidade · ${money(item.unit_price)} · Total: ${money(item.total)}</span></article>`).join('');
  byId('assistant-answer').textContent=`Nota ${openedDocument.number} aberta. Valor devedor ${money(openedDocument.outstanding_amount)}.`;
}
async function showEmployeeHistory(){
  const data=await (await employeeRequest('/history')).json();byId('employee-history').hidden=false;
  byId('employee-events').innerHTML=data.events.map(event=>`<article class="history-event"><strong>${safe(event.action)}</strong><p>${safe(event.detail)}</p><small>R.E. ${safe(event.re)} · ${new Date(event.time).toLocaleString('pt-BR')}</small></article>`).join('');
  byId('assistant-answer').textContent='Histórico de acessos desta sessão exibido.';
}
async function downloadEmployeePdf(){
  if(!openedDocument)throw new Error('Abra uma nota antes de baixar o PDF.');
  const response=await employeeRequest('/documents/'+encodeURIComponent(openedDocument.id)+'/pdf');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=`autoflow-nota-demo-${openedDocument.number}.pdf`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  byId('assistant-answer').textContent='PDF fictício autorizado para download.';
}
async function executeEmployeeCommand(text){
  if(commandBusy||!employee)return;
  cancelVoiceInput();commandBusy=true;byId('employee-message').textContent='Consultando…';byId('employee-command').value=text;
  const submit=byId('command-form').querySelector('[type="submit"]');submit.disabled=true;submit.textContent='Consultando…';byId('command-form').setAttribute('aria-busy','true');
  const normalized=text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
  try{
    if(/^(sair|encerrar sessao)[.!?]*$/.test(normalized)){await employeeLogout();return;}
    if(/(historico|auditoria)/.test(normalized)){await showEmployeeHistory();return;}
    if(/(baixar|download).*(pdf|nota|documento)/.test(normalized)){await downloadEmployeePdf();return;}
    if(/(endereco|telefone|divida total|total da divida|parcelas)/.test(normalized)){if(!openedDocument)throw new Error('Abra uma nota para consultar sua ficha.');if(!employee.full_record)throw new Error('Endereço, telefone, dívida total e parcelas são exclusivos da diretoria.');byId('assistant-answer').textContent=`${openedDocument.debtor_name}. Endereço: ${openedDocument.address}. Telefone: ${openedDocument.phone}. Dívida total: ${money(openedDocument.total_debt)}. Parcelas restantes: ${openedDocument.remaining_installments}.`;return;}
    if(/qual.*valor/.test(normalized)){if(!openedDocument)throw new Error('Abra uma nota para consultar seu valor.');byId('assistant-answer').textContent=`A nota ${openedDocument.number} tem valor devedor de ${money(openedDocument.outstanding_amount)}.`;return;}
    const opening=normalized.match(/^(?:abrir|abra|mostrar|mostre)\s+(?:(?:a|o|nota|resultado)\s+)*(primeir[ao]|segund[ao]|terceir[ao]|quart[ao]|[1-9])(?:\s+(?:nota|resultado))?[.!?]*$/);
    if(opening){const index=/^primeir/.test(opening[1])?0:/^segund/.test(opening[1])?1:/^terceir/.test(opening[1])?2:/^quart/.test(opening[1])?3:Number(opening[1])-1;if(!employeeResults[index])throw new Error('Esse resultado não está disponível. Faça uma busca primeiro.');await openEmployeeDocument(employeeResults[index].id);return;}
    const data=await (await employeeRequest('/query','POST',{text})).json();employeeResults=data.documents;openedDocument=null;byId('document-detail').hidden=true;byId('employee-history').hidden=true;byId('assistant-answer').textContent=data.message;
    byId('document-results').innerHTML=data.documents.map((document,index)=>`<button type="button" class="document-result" data-document="${safe(document.id)}"><span>0${index+1} / NOTA ${safe(document.number)}</span><strong>${money(document.outstanding_amount)}</strong><p>${safe(document.debtor_name)} · ${safe(document.unit)}</p><small>${safe(document.tax_type)} ${safe(document.tax_id)} · ${safe(document.date)}</small><b>Abrir nota ↗</b></button>`).join('');
    document.querySelectorAll('[data-document]').forEach(button=>button.onclick=()=>openEmployeeDocument(button.dataset.document).catch(error=>byId('employee-message').textContent=error.message));
    byId('employee-message').textContent='';
  }catch(error){byId('employee-message').textContent=error.name==='TimeoutError'?'O servidor está demorando para responder. Tente consultar novamente.':error.message;}finally{commandBusy=false;submit.disabled=false;submit.textContent='Consultar →';byId('command-form').setAttribute('aria-busy','false');if(byId('employee-message').textContent==='Consultando…')byId('employee-message').textContent='';}
}
byId('command-form').onsubmit=event=>{event.preventDefault();executeEmployeeCommand(byId('employee-command').value);};
document.querySelectorAll('[data-command]').forEach(button=>button.onclick=()=>executeEmployeeCommand(button.dataset.command));
byId('show-history').onclick=()=>showEmployeeHistory().catch(error=>byId('employee-message').textContent=error.message);
byId('download-pdf').onclick=()=>downloadEmployeePdf().catch(error=>byId('employee-message').textContent=error.message);

function renderCollectionReceipt(receipt){
  byId('collection-preview').hidden=false;
  byId('collection-status').textContent=receipt.status+' · '+receipt.id;
  byId('collection-sender').textContent=receipt.sender;
  byId('collection-recipient').textContent=receipt.recipient;
  byId('collection-subject').textContent=receipt.subject;
  byId('collection-body').textContent=receipt.body;
  byId('collection-attachment').textContent=receipt.attachment.filename;
  byId('collection-attachment').href='/assistant/collections/'+encodeURIComponent(receipt.id)+'/pdf';
}
async function loadCollections(){
  const csrf=employeeCsrf;
  const data=await (await employeeRequest('/collections')).json();
  if(!employee||csrf!==employeeCsrf)return;
  byId('collection-history').innerHTML=(data.receipts||[]).map(receipt=>`<article class="collection-history-item"><span class="collection-sent">ENVIO SIMULADO</span><strong>Nota ${safe(receipt.number)} · ${money(receipt.amount)}</strong><p>${safe(receipt.recipient)}</p><small>${safe(receipt.id)} · ${new Date(receipt.created_at).toLocaleString('pt-BR')}</small><button type="button" class="secondary" data-collection="${safe(receipt.id)}">Ver e-mail e anexo ↗</button></article>`).join('');
  document.querySelectorAll('[data-collection]').forEach(button=>button.onclick=()=>{const receipt=data.receipts.find(r=>r.id===button.dataset.collection);if(receipt)renderCollectionReceipt(receipt);});
}
async function generateCollection(){
  if(collectionBusy||!openedDocument||!employee)return;
  cancelVoiceInput();collectionBusy=true;const csrf=employeeCsrf;
  const button=byId('generate-collection');button.disabled=true;button.textContent='Gerando nota e e-mail…';
  byId('collection-message').textContent='Gerando o PDF e preenchendo a cobrança…';
  try{
    const receipt=await (await employeeRequest('/documents/'+encodeURIComponent(openedDocument.id)+'/collection','POST',{})).json();
    if(!employee||csrf!==employeeCsrf)return;
    renderCollectionReceipt(receipt);
    byId('collection-message').textContent=receipt.replayed?'Esta cobrança já foi simulada nesta sessão. O mesmo protocolo foi preservado.':'Nota gerada, e-mail preenchido e envio simulado concluído automaticamente.';
    await loadCollections();
  }catch(error){if(employee&&csrf===employeeCsrf)byId('collection-message').textContent=error.message;}
  finally{collectionBusy=false;button.disabled=false;button.textContent='Gerar nota e enviar cobrança →';}
}
byId('generate-collection').onclick=generateCollection;

function setupRecognition(){
  const supported=window.SpeechRecognition||window.webkitSpeechRecognition;
  byId('voice-start').disabled=!supported;
  if(!supported)byId('voice-status').textContent='Reconhecimento de voz indisponível neste navegador. Você pode digitar a consulta.';
}
function recognizedDigits(text){
  const words={zero:'0',um:'1',uma:'1',dois:'2',duas:'2',tres:'3',quatro:'4',cinco:'5',seis:'6',sete:'7',oito:'8',nove:'9'};
  let normalized=text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  normalized=normalized.replace(/\b(zero|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove)\b/g,word=>words[word]);
  return (normalized.match(/\d/g)||[]).join('');
}
function stopWithVoiceMessage(message){
  const draft=byId('employee-command').value;
  cancelVoiceInput();voiceResume=Boolean(draft.trim());
  byId('voice-status').textContent=message+' O texto foi preservado. Clique em Falar para continuar.';
}
function armVoiceIdleTimer(epoch){
  clearTimeout(voiceIdleTimer);
  voiceIdleTimer=setTimeout(()=>{if(voiceEpoch===epoch&&voiceActive)stopWithVoiceMessage('Captura pausada após 90 segundos sem novos trechos.');},90000);
}
function startVoiceSession(epoch){
  if(epoch!==voiceEpoch||!voiceActive||voiceCancelled||voiceSubmitted||!employee)return;
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  const engine=new Recognition();recognition=engine;
  voiceEvent('session.created');
  engine.lang='pt-BR';engine.continuous=true;engine.interimResults=true;engine.maxAlternatives=1;
  let ended=false;
  const current=()=>!ended&&epoch===voiceEpoch&&recognition===engine&&voiceActive&&!voiceCancelled&&!voiceSubmitted&&Boolean(employee);
  engine.onstart=()=>{if(!current()){engine.abort();return;}voiceEvent('start');listening=true;byId('voice-start').setAttribute('aria-pressed','true');byId('voice-stop').hidden=false;byId('voice-status').textContent='Ouvindo… pode fazer pausas. Diga “consulte” somente ao terminar.';};
  engine.onresult=event=>{
    if(!current())return;
    const results=Array.from(event.results);
    const transcript=results.map(result=>result[0].transcript.trim()).filter(Boolean).join(' ');
    const text=[voicePrefix,transcript].filter(Boolean).join(' ');
    byId('employee-command').value=text;
    if(transcript)armVoiceIdleTimer(epoch);
    const digits=recognizedDigits(text);
    voiceEvent('result',{digits:digits.length,segments:results.length,finalSegments:results.filter(result=>result.isFinal).length});
    byId('voice-status').textContent=(digits?`Reconhecido: ${digits} · ${digits.length} dígitos. `:'Ouvindo… ')+ 'Pode continuar. Diga “consulte” para buscar.';
    // Uma hipótese parcial nunca autoriza uma consulta.
    const finalText=[voicePrefix,...results.filter(result=>result.isFinal).map(result=>result[0].transcript.trim())].filter(Boolean).join(' ');
    const confirmation=finalText.match(/\bconsulte[.!?,;:]*\s*$/i);
    const hasInterim=results.some(result=>!result.isFinal&&result[0].transcript.trim());
    if(confirmation&&!hasInterim){
      const command=finalText.slice(0,confirmation.index).trim();
      if(!command){byId('voice-status').textContent='Diga a nota ou o identificador antes de “consulte”.';return;}
      voiceSubmitted=true;executeEmployeeCommand(command);
    }
  };
  engine.onerror=event=>{
    if(!current())return;
    voiceEvent('error',{code:event.error});
    if(event.error==='no-speech'||event.error==='aborted'){
      byId('voice-status').textContent='Aguardando você continuar… os dígitos já ditados foram preservados.';
      return;
    }
    const messages={'not-allowed':'Microfone não autorizado.','service-not-allowed':'O serviço de voz não foi autorizado pelo navegador.','audio-capture':'O navegador não conseguiu acessar o microfone.','network':'O serviço de reconhecimento do Chrome perdeu a conexão.','language-not-supported':'O serviço de voz não oferece português neste navegador.'};
    stopWithVoiceMessage(messages[event.error]||'O serviço de voz interrompeu a captura ('+event.error+').');
  };
  engine.onend=()=>{
    if(ended)return;ended=true;
    if(epoch!==voiceEpoch||recognition!==engine||!voiceActive||voiceCancelled||voiceSubmitted||!employee)return;
    voiceEvent('end.restart',{digits:recognizedDigits(byId('employee-command').value).length});
    listening=false;recognition=null;
    voicePrefix=byId('employee-command').value.trim();
    byId('voice-status').textContent='Continuando a escuta… sua transcrição foi preservada.';
    // Uma instância nova evita estado encerrado e eventos atrasados da anterior.
    voiceRestartTimer=setTimeout(()=>startVoiceSession(epoch),250);
  };
  try{engine.start();}catch(error){if(current())stopWithVoiceMessage('Não foi possível iniciar a captura ('+error.name+').');}
}
byId('voice-start').onclick=()=>{
  if(!employee||commandBusy||!(window.SpeechRecognition||window.webkitSpeechRecognition))return;
  if(voiceActive){cancelVoiceInput();byId('voice-status').textContent='Microfone parado. Nenhuma consulta foi enviada.';return;}
  voicePrefix=voiceResume?byId('employee-command').value.trim():'';voiceResume=false;
  voiceCancelled=false;voiceSubmitted=false;voiceActive=true;const epoch=++voiceEpoch;
  armVoiceIdleTimer(epoch);byId('voice-status').textContent='Ativando microfone…';startVoiceSession(epoch);
};
byId('voice-stop').onclick=()=>{const draft=byId('employee-command').value;cancelVoiceInput();voiceResume=Boolean(draft.trim());byId('voice-status').textContent='Microfone parado. Nenhuma consulta foi enviada. Clique em Falar para continuar ou em Consultar para enviar o texto.';};
byId('employee-command').addEventListener('input',()=>{if(voiceActive){cancelVoiceInput();byId('voice-status').textContent='Edição manual. Corrija o comando e clique em Consultar.';}});
window.addEventListener('pagehide',cancelVoiceInput);
employeeRequest('/me').then(response=>response.json()).then(showEmployee).catch(()=>{});
