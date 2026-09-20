/* the data's version, stamped by deploy.sh: every data fetch carries it so a
   deploy's files are cached until the next deploy changes the key */
const DATA_V="dev";
const withV=p=>p+(p.includes("?")?"&":"?")+"v="+DATA_V;
/* the tape page: loads the panel, the founders and the events for the
   reader's tier, then renders the same block the home page carries */
const $=s=>document.querySelector(s);
function openPro(){location.href="/pro/";}
async function fetchText(paths){
  /* A PAGE IS NOT A FILE: the host answers an unknown path with the home
     page and a 200; a reply that starts like HTML is a miss and the next
     path is tried (2026-09-14: /pro/history/XYZ.csv did not exist, and the
     stake chart parsed the home page). */
  for(const p of paths){try{const q=await fetch(withV(p));if(!q.ok)continue;const t=await q.text();if(/^\s*</.test(t))continue;return t;}catch(e){}}
  return null;
}
async function boot(){
  hit("view","page");   /* THE PAGE COUNTS ITS OWN VISITORS, like the home page: the same beacon, shared */
  let me=null;
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)me=await q.json();}catch(e){}
  state.pro=!!(me&&me.pro);
  document.body.classList.toggle("pro",state.pro);   /* the letter's band is hidden for Pro */
  {const b=document.querySelector(".topnav .gopro");if(b&&state.pro){b.textContent="Account";b.setAttribute("href","/account/");b.title="Your letter, your watches, your billing";}}
  const [p,f,e]=await Promise.all([
    fetchText(state.pro?["/pro/universe.csv","/universe.csv","/panel.csv"]:["/universe.csv","/panel.csv"]),
    fetchText(["/founders.csv"]),
    fetchText(state.pro?["/pro/events.csv","/events-free.csv"]:["/events-free.csv"]),
  ]);
  if(p)PANEL=mapPanel(parseCSV(p));
  if(f)for(const r of parseCSV(f)){if(r.ticker)FOUNDERS[r.ticker.toUpperCase()]={f:(r.founder||"").toLowerCase(),ev:r.evidence||"",src:r.source||""};}
  if(e)EVENTS=mapEvents(parseCSV(e));
  {const el=$("#tg-f");if(el)el.addEventListener("change",()=>{state.ev.f=el.checked;renderActivity();});}   /* the kind chips are drawn by renderActivity and wire themselves */
  document.querySelectorAll("#actwin .win").forEach(c=>c.addEventListener("click",()=>setWin(c.dataset.win)));
  renderActivity();
  /* THE CONFIRMATION IS THE BOX. After the click, the form gives way to a
     statement a reader cannot miss: on the list, next Monday, this page
     until then. */
  if(new URLSearchParams(location.search).get("subscribed")==="1"){
    const box=$("#subscribe");
    if(box)box.innerHTML=`<div class="done"><h3>You're on the list.</h3><p>The letter goes out once a week: who bought, who cut a stake, who sold on a plan, founders first. Until then, this page is the tape. Every letter carries an unsubscribe link.</p></div>`;
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
state.ev={win:"7",f:true,kind:"all",moved:false,sort:{key:null,dir:-1}};
boot();
