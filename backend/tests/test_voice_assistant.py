from time import monotonic
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.voice_assistant import sessions, lock, TTL
from test_invoices import client


def login(http,re="1001"):
    response=http.post('/assistant/login',json={'re':re,'password':'AutoflowDemo2026!'})
    assert response.status_code==200,response.text
    return {'X-Voice-CSRF':response.json()['csrf_token']}


def test_login_requires_re_password_and_cookie(client):
    http,_=client
    assert http.get('/assistant/me').status_code==401
    assert http.post('/assistant/login',json={'re':'1001','password':'wrong'}).status_code==401
    assert http.post('/assistant/login',json={'re':'9999','password':'AutoflowDemo2026!'}).status_code==401
    assert http.post('/assistant/login',json={'re':'1001','password':'AutoflowDemo2026!','role':'Supervisor'}).status_code==422
    secret='sensitive-test-'*20
    rejected=http.post('/assistant/login',json={'re':'1001','password':secret})
    assert rejected.status_code==422 and secret not in rejected.text
    headers=login(http)
    assert http.get('/assistant/me').json()['profile']['role']=='Operador'
    assert http.post('/assistant/query',json={'text':'listar minhas notas'}).status_code==403
    result=http.post('/assistant/query',headers=headers,json={'text':'listar minhas notas'})
    assert result.status_code==200 and result.json()['count']==2


@pytest.mark.parametrize('re,expected',[('1001',1),('2001',2),('3001',2)])
def test_same_query_respects_profile(client,re,expected):
    http,_=client; headers=login(http,re)
    response=http.post('/assistant/query',headers=headers,json={'text':'Busque as notas do CPF 00000000001'})
    assert response.status_code==200 and response.json()['count']==expected
    if re=='3001':
        assert '00000000001' not in response.text
        assert all(document['tax_id'].startswith('*') and not document['can_download'] for document in response.json()['documents'])


def test_operator_cannot_open_or_download_other_unit_even_with_header(client):
    http,_=client; login(http)
    assert http.get('/assistant/documents/nf-102',headers={'X-RE':'2001'}).status_code==404
    assert http.get('/assistant/documents/nf-102/pdf').status_code==404
    assert http.get('/assistant/documents/nf-101').status_code==200
    pdf=http.get('/assistant/documents/nf-101/pdf')
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    assert 'no-store' in pdf.headers['cache-control']


def test_auditor_download_denied_and_identifiers_masked(client):
    http,_=client; login(http,'3001')
    response=http.get('/assistant/documents/nf-103')
    assert '12345678000195' not in response.text
    assert response.json()['tax_id'].endswith('95')
    assert http.get('/assistant/documents/nf-103/pdf').status_code==403


def test_voice_transcript_digit_words_and_punctuation(client):
    http,_=client; headers=login(http,'2001')
    phrases=['Notas do C P F zero zero zero zero zero zero zero zero zero zero um','Busque CPF 000.000.000-01']
    for text in phrases:
        result=http.post('/assistant/query',headers=headers,json={'text':text})
        assert result.status_code==200 and result.json()['count']==2
    assert http.post('/assistant/query',headers=headers,json={'text':'nota um zero quatro'}).json()['documents'][0]['number']=='104'
    assert http.post('/assistant/query',headers=headers,json={'text':'última nota do CPF 00000000001'}).json()['documents'][0]['number']=='102'
    assert http.post('/assistant/query',headers=headers,json={'text':'notas do CNPJ 12.345.678/0001-95'}).json()['count']==2


@pytest.mark.parametrize('text',['CPF 2223457899','CNPJ 123','qualquer coisa','CPF 00000000001 e 00000000002'])
def test_unclear_identifiers_not_guessed(client,text):
    http,_=client; headers=login(http)
    assert http.post('/assistant/query',headers=headers,json={'text':text}).status_code==422


def test_document_and_pdf_require_authentication(client):
    http,_=client
    assert http.get('/assistant/documents/nf-101').status_code==401
    assert http.get('/assistant/documents/nf-101/pdf').status_code==401
    assert http.get('/assistant/history').status_code==401


def test_logout_revokes_session_and_history_is_scoped(client):
    http,_=client; headers=login(http)
    http.post('/assistant/query',headers=headers,json={'text':'nota 101'})
    events=http.get('/assistant/history').json()['events']
    assert any(event['action']=='query' for event in events)
    assert all(event['re']=='1001' for event in events)
    assert '00000000001' not in str(events)
    assert http.post('/assistant/logout',headers=headers).status_code==204
    assert http.get('/assistant/documents/nf-101').status_code==401
    login(http,'2001')
    assert all(event['re']=='2001' for event in http.get('/assistant/history').json()['events'])


def test_expiry_and_microphone_policy(client):
    http,_=client; login(http)
    with lock:
        for session in sessions.values(): session['started']=monotonic()-TTL-1
    assert http.get('/assistant/me').status_code==401
    page=http.get('/assistente')
    assert page.status_code==200 and 'microphone=(self)' in page.headers['permissions-policy']
    assert 'microphone=()' in http.get('/').headers['permissions-policy']
    assert http.get('/assets/assistant.js').status_code==200


def test_voice_cookie_does_not_unlock_private_api(client):
    http,_=client; login(http,'2001'); http.headers.pop('X-API-Key')
    assert http.get('/api/v1/invoices').status_code==401
