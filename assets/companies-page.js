/* the companies page: the screener in full. Loads the same files the home
   page loads for the reader's tier and renders the same table, unlimited */
const DATA_V="dev";
const withV=p=>p+(p.includes("?")?"&":"?")+"v="+DATA_V;
const $=s=>document.querySelector(s);
function openPro(){location.href="/pro/";}
function openCompany(tk){location.href="/company/"+tk+"/";}
/* one masthead button, two lives, on this page too; a signed-in reader's watches beside it */
function nav(me){
  const b=document.querySelector(".topnav .gopro");if(!b)return;
  if(me&&me.pro){b.textContent="Account";b.setAttribute("href","/account/");b.title="Your letter, your watches, your billing";}
}
let SCREEN_COUNTS=null,TABLE_LIMIT=0;
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
  nav(me);
  /* THE LIST IS ENOUGH (2026-09-14). The last move and never-sold are in
     the list from the build, so this page loads no history and no events:
     four files under a megabyte instead of the archive, and the table
     draws in well under a second. */
  const [p,f,c,pr]=await Promise.all([
    fetchText(state.pro?["/pro/universe.csv","/universe.csv","/panel.csv"]:["/universe.csv","/panel.csv"]),
    fetchText(["/founders.csv"]),
    fetchText(["/screen-counts.json"]),
    fetchText(["/prices.csv"]),
  ]);
  if(p){PANEL=mapPanel(parseCSV(p));state.live.panel=true;}
  /* NO NEVER-SOLD SWITCH HERE (2026-09-17): the "Never sold" screen chip above
     the table is the same filter; two controls for one idea confused the
     page. The list's never-sold fact still feeds the chip (r.pns). */
  /* THE PRICES MAKE THE VALUE AND THE MARKET CAP. Without them the two
     columns were blank on this page (2026-09-14). */
  if(pr){const m={};let asof="";for(const r of parseCSV(pr)){const c=num(r.close);if(r.ticker&&c){m[r.ticker.toUpperCase()]=c;asof=r.as_of||asof;}}
    if(Object.keys(m).length){PRICES=m;PRICES_ASOF=asof;state.live.prices=true;}}
  applyPrices();
  if(f){for(const r of parseCSV(f)){if(r.ticker)FOUNDERS[r.ticker.toUpperCase()]={f:(r.founder||"").toLowerCase(),ev:r.evidence||"",src:r.source||""};}
    state.live.founders=true;   /* the Founders only switch shows once the file is here (it was never set on this page: 2026-09-17) */}
  if(c){try{SCREEN_COUNTS=JSON.parse(c);}catch(x){}}
  const q=$("#q");if(q)q.addEventListener("input",()=>{state.q=q.value;renderTable();});
  /* THE CONTROLS ARE QUESTIONS (2026-09-21): a chip sets its group; the address follows */
  document.querySelectorAll(".chip[data-g][data-v]").forEach(b=>b.addEventListener("click",()=>setGroup(b.dataset.g,b.dataset.v)));
  document.querySelectorAll("th.sortable").forEach(th=>th.addEventListener("click",()=>{
    const key=th.dataset.key;
    if(state.sort.key===key)state.sort.dir=-state.sort.dir;else state.sort={key,dir:-1};
    renderTable();
  }));
  const ex=$("#export");if(ex)ex.addEventListener("click",()=>exportTable());
  /* ONE SCREEN, ONE ADDRESS: a screen page carries its preset, written by the builder;
     a shared link carries its choices in the query; either opens with the chips on */
  const preset=(typeof window!=="undefined"&&window.SCREEN_PRESET)||"";
  if(preset&&PRESETS[preset]){Object.assign(state,DEFAULTS,PRESETS[preset]);state.screen=preset;}
  else readAddress();
  const qq=$("#q");if(qq)qq.addEventListener("input",()=>{if(/^\/screens\//.test(location.pathname)){screenAddress();}});
  renderTable();
  /* the rows the builder wrote beneath for a crawler step aside once the table above is drawn */
  const st=document.getElementById("sstatic");if(st)st.style.display="none";
}
state.sort={key:"val",dir:-1};state.q="";Object.assign(state,DEFAULTS);state.screen="";state.live={panel:false,hist:false,events:false,founders:false,prices:false};
boot();
