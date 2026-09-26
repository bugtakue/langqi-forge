// Deliberately tiny grader fault fixture. NOT a candidate application/template.
// Nothing under sensitivity/ may be included in an agent submission.
const http=require('node:http'), fs=require('node:fs'), crypto=require('node:crypto');
const defect=fs.readFileSync('variant.txt','utf8').trim();
const empty=()=>({accounts:{},sessions:{}});
let volatile=empty();
function read(){return defect==='volatile'?volatile:fs.existsSync('db.json')?JSON.parse(fs.readFileSync('db.json','utf8')):empty()}
function save(db){if(defect==='volatile'){volatile=db;return} fs.writeFileSync('db.tmp',JSON.stringify(db));fs.renameSync('db.tmp','db.json')}
const html=`<!doctype html><html><body>
<form><label>Identity<input name=identity></label><label>Secret<input name=secret type=password></label>
<button name=register>Register</button><button name=login>Login</button></form>
<button id=out>Sign out</button><output id=user aria-label="Current user"></output><p role=alert></p>
<script>
const form=document.querySelector('form'), user=document.querySelector('#user'), alert=document.querySelector('[role=alert]');
async function state(){const d=await(await fetch('/state')).json();user.textContent=d.user||''}
form.onsubmit=async e=>{e.preventDefault();const r=await fetch('/'+e.submitter.name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});alert.textContent=r.ok?'':'Invalid credentials';await state()};
out.onclick=async()=>{await fetch('/logout',{method:'POST'});await state()};state();
</script></body></html>`;
http.createServer(async(req,res)=>{
  const reply=(code,data,headers={})=>{res.writeHead(code,{'Content-Type':'application/json',...headers});res.end(JSON.stringify(data))};
  if(defect==='blank'){res.end('');return}
  if(defect==='200-only'){res.end('OK');return}
  if(req.method==='GET'&&req.url==='/'){res.writeHead(200,{'Content-Type':'text/html'});res.end(html);return}
  const db=read(), token=(req.headers.cookie||'').split('sid=')[1]?.split(';')[0];
  if(req.url==='/state'){reply(200,{user:defect==='session-loss'?'':db.sessions[token]||''});return}
  if(req.url==='/logout'){delete db.sessions[token];save(db);reply(200,{}, {'Set-Cookie':'sid=; Max-Age=0; Path=/; HttpOnly'});return}
  let raw='';for await(const chunk of req)raw+=chunk;
  let body;try{body=JSON.parse(raw)}catch{reply(400,{});return}
  const {identity,secret}=body;
  if(req.url==='/register'){
    if(!identity||!secret||db.accounts[identity]){reply(400,{});return}
    db.accounts[identity]=secret;save(db);reply(200,{});return;
  }
  if(req.url==='/login'){
    if(!identity||db.accounts[identity]!==secret){reply(401,{});return}
    const sid=crypto.randomBytes(20).toString('hex');db.sessions[sid]=identity;
    // Reproduces a response object accidentally replacing the whole database.
    save(defect==='overwrite-db'?{accounts:{},sessions:db.sessions}:db);
    reply(200,{}, {'Set-Cookie':'sid='+sid+'; HttpOnly; Path=/; SameSite=Lax'});return;
  }
  reply(404,{});
}).listen(3000,'127.0.0.1');
