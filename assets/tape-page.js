/* the data's version, stamped by deploy.sh: every data fetch carries it so a
   deploy's files are cached until the next deploy changes the key */
const DATA_V="dev";
const withV=p=>p+(p.includes("?")?"&":"?")+"v="+DATA_V;
/* the tape page: loads the panel, the founders and the events for the
   reader's tier, then renders the same block the home page carries */
const $=s=>document.querySelector(s);
function openPro(){location.href="/#pro";}
async function fetchText(paths){
  for(const p of paths){try{const q=await fetch(withV(p));if(q.ok)return await q.text();}catch(e){}}
  return null;
}
async function boot(){
  let me=null;
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)me=await q.json();}catch(e){}
  state.pro=!!(me&&me.pro);
  const [p,f,e]=await Promise.all([
    fetchText(state.pro?["/pro/universe.csv","/universe.csv","/panel.csv"]:["/universe.csv","/panel.csv"]),
    fetchText(["/founders.csv"]),
    fetchText(state.pro?["/pro/events.csv","/events-free.csv"]:["/events-free.csv"]),
  ]);
  if(p)PANEL=mapPanel(parseCSV(p));
  if(f)for(const r of parseCSV(f)){if(r.ticker)FOUNDERS[r.ticker.toUpperCase()]={f:(r.founder||"").toLowerCase(),ev:r.evidence||"",src:r.source||""};}
  if(e)EVENTS=mapEvents(parseCSV(e));
  for(const [id,key] of [["tg-f","f"],["tg-buys","buys"],["tg-nocomp","nocomp"]]){const el=$("#"+id);if(el)el.addEventListener("change",()=>{state.ev[key]=el.checked;renderActivity();});}
  document.querySelectorAll("#actwin .win").forEach(c=>c.addEventListener("click",()=>setWin(c.dataset.win)));
  renderActivity();
  /* THE CONFIRMATION IS THE BOX. After the click, the form gives way to a
     statement a reader cannot miss: on the list, next Monday, this page
     until then. */
  if(new URLSearchParams(location.search).get("subscribed")==="1"){
    const box=$("#subscribe");
    if(box)box.innerHTML=`<h3>You're on the list.</h3><div class="rule"></div><p>The Monday tape goes out next Monday morning: who bought, who cut a stake, who sold on a plan, founders first.</p><p>Until then, this page is the tape.</p><div class="fine">Every letter carries an unsubscribe link.</div>`;
    history.replaceState(null,"",location.pathname);
  }
  if(new URLSearchParams(location.search).get("subscribed")==="check"){const m=$("#submsg");if(m)m.textContent="Check your inbox: one click confirms it.";}
  if(new URLSearchParams(location.search).get("subscribed")==="error"){const m=$("#submsg");if(m)m.textContent="The list refused the add; write to hello@founderledequities.com and I'll fix it.";}
  if(new URLSearchParams(location.search).get("subscribed")==="expired"){const m=$("#submsg");if(m)m.textContent="That link expired; enter your address again.";}
}
async function subscribe(ev){
  ev.preventDefault();
  const email=($("#subemail").value||"").trim(),m=$("#submsg"),btn=$("#subform button");
  if(!email||btn.disabled)return false;
  /* one submission per address: the button and the field lock once sent */
  btn.disabled=true;btn.textContent="Sending…";
  try{
    const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});
    const j=await q.json();
    m.textContent=j.message||"Check your inbox: one click confirms it.";
    if(j.ok){$("#subemail").disabled=true;btn.textContent="Sent";}
    else{btn.disabled=false;btn.textContent="Send it";}
  }catch(e){m.textContent="Something went wrong; write to hello@founderledequities.com.";btn.disabled=false;btn.textContent="Send it";}
  return false;
}
function openCompany(tk){location.href="/company/"+tk+"/";}
state.ev={win:"7",f:true,buys:false,nocomp:false};
boot();
