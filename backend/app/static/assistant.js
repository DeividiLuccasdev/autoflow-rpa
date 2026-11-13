const byId=id=>document.getElementById(id);
const safe=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money=value=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let employee=null, employeeCsrf='', employeeResults=[], openedDocument=null, recognition=null, listening=false, commandBusy=false;

async function employeeRequest(path,method='GET',body){
  const response=await fetch('/assistant'+path,{method,headers:{...(method==='POST'?{'X-Voice-CSRF':employeeCsrf}:{}),...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(90000)});
  if(!response.ok){const data=await response.json();if(response.status===401)clearEmployee();throw new Error(typeof data.detail==='string'?data.detail:'Confira os campos informados.');}
  return response;
}
function clearEmployee(){
  recognition?.abort();employee=null;employeeCsrf='';employeeResults=[];openedDocument=null;
  byId('assistant-panel').hidden=true;byId('login-panel').hidden=false;byId('document-detail').hidden=true;byId('employee-history').hidden=true;
  byId('document-results').replaceChildren();byId('document-fields').replaceChildren();byId('document-items').replaceChildren();byId('employee-events').replaceChildren();byId('assistant-answer').textContent='';byId('employee-command').value='';
}
function showEmployee(data){
  employee=data.profile;employeeCsrf=data.csrf_token;byId('login-panel').hidden=true;byId('assistant-panel').hidden=false;
  byId('employee-name').textContent=`R.E. ${employee.re} · ${employee.role}`;
  byId('employee-access').textContent=`${employee.name} · Unidades: ${employee.units.join(' e ')} · ${employee.download?'Download autorizado':'Sem download de PDF'} · ${employee.full_record?'Ficha completa de cobrança':'Nota, valor devedor e razão social'}`;
  byId('employee-message').textContent='';setupRecognition();
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
  if(commandBusy||!employee)return;commandBusy=true;byId('employee-message').textContent='';byId('employee-command').value=text;
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
  }catch(error){byId('employee-message').textContent=error.message;}finally{commandBusy=false;}
}
byId('command-form').onsubmit=event=>{event.preventDefault();executeEmployeeCommand(byId('employee-command').value);};
document.querySelectorAll('[data-command]').forEach(button=>button.onclick=()=>executeEmployeeCommand(button.dataset.command));
byId('show-history').onclick=()=>showEmployeeHistory().catch(error=>byId('employee-message').textContent=error.message);
byId('download-pdf').onclick=()=>downloadEmployeePdf().catch(error=>byId('employee-message').textContent=error.message);

function setupRecognition(){
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Recognition){byId('voice-start').disabled=true;byId('voice-status').textContent='Este navegador não oferece reconhecimento de voz. Continue digitando ou use um navegador compatível.';return;}
  if(recognition)return;
  recognition=new Recognition();recognition.lang='pt-BR';recognition.continuous=false;recognition.interimResults=false;recognition.maxAlternatives=1;
  recognition.onstart=()=>{listening=true;byId('voice-start').setAttribute('aria-pressed','true');byId('voice-stop').hidden=false;byId('voice-status').textContent='Ouvindo… diga um comando. Pode parar o microfone a qualquer momento.';};
  recognition.onresult=event=>{const text=event.results[0][0].transcript;byId('employee-command').value=text;byId('voice-status').textContent='Entendi: '+text;executeEmployeeCommand(text);};
  recognition.onend=()=>{listening=false;byId('voice-start').setAttribute('aria-pressed','false');byId('voice-stop').hidden=true;};
  recognition.onerror=event=>{byId('voice-status').textContent=event.error==='not-allowed'?'Microfone não autorizado. Você pode continuar digitando.':event.error==='no-speech'?'Não ouvi um comando. Tente novamente ou digite.':'Não foi possível transcrever o áudio. Continue digitando ou tente novamente.';};
}
byId('voice-start').onclick=()=>{if(!employee||!recognition||commandBusy)return;if(listening){recognition.stop();return;}try{recognition.start();}catch{byId('voice-status').textContent='Aguarde o microfone ficar disponível ou digite o comando.';}};
byId('voice-stop').onclick=()=>recognition?.abort();
window.addEventListener('pagehide',()=>recognition?.abort());
employeeRequest('/me').then(response=>response.json()).then(showEmployee).catch(()=>{});
