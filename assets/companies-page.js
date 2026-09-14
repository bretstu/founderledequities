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
  for(const p of paths){try{const q=await fetch(withV(p));if(q.ok)return await q.text();}catch(e){}}
  return null;
}
async function boot(){
  hit("view","page");   /* THE PAGE COUNTS ITS OWN VISITORS, like the home page: the same beacon, shared */
  let me=null;
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)me=await q.json();}catch(e){}
  state.pro=!!(me&&me.pro);
  nav(me);
  const [p,f,h,e,c,pr]=await Promise.all([
    fetchText(state.pro?["/pro/universe.csv","/universe.csv","/panel.csv"]:["/universe.csv","/panel.csv"]),
    fetchText(["/founders.csv"]),
    fetchText(state.pro?["/pro/history-lite.csv","/history-free-lite.csv"]:["/history-free-lite.csv"]),
    fetchText(state.pro?["/pro/events.csv","/events-free.csv"]:["/events-free.csv"]),
    fetchText(["/screen-counts.json"]),
    fetchText(["/prices.csv"]),
  ]);
  if(p){PANEL=mapPanel(parseCSV(p));state.live.panel=true;}
  /* THE PRICES MAKE THE VALUE AND THE MARKET CAP. Without them the two
     columns were blank on this page (2026-09-14). */
  if(pr){const m={};let asof="";for(const r of parseCSV(pr)){const c=num(r.close);if(r.ticker&&c){m[r.ticker.toUpperCase()]=c;asof=r.as_of||asof;}}
    if(Object.keys(m).length){PRICES=m;PRICES_ASOF=asof;state.live.prices=true;}}
  applyPrices();
  if(f)for(const r of parseCSV(f)){if(r.ticker)FOUNDERS[r.ticker.toUpperCase()]={f:(r.founder||"").toLowerCase(),ev:r.evidence||"",src:r.source||""};}
  if(h){HIST=mapHistory(parseCSV(h));state.live.hist=true;}
  if(e)EVENTS=mapEvents(parseCSV(e));
  if(c){try{SCREEN_COUNTS=JSON.parse(c);}catch(x){}}
  const q=$("#q");if(q)q.addEventListener("input",()=>{state.q=q.value;renderTable();});
  document.querySelectorAll("[data-min]").forEach(b=>b.addEventListener("click",()=>{state.min=+b.dataset.min;document.querySelectorAll("[data-min]").forEach(x=>x.classList.toggle("on",x===b));renderTable();}));
  wireSw("fchip",()=>{state.tbF=!state.tbF;renderTable();});
  wireSw("hchip",()=>{state.tbH=!state.tbH;renderTable();});
  document.querySelectorAll("th.sortable").forEach(th=>th.addEventListener("click",()=>{
    const key=th.dataset.key;
    if(state.sort.key===key)state.sort.dir=-state.sort.dir;else state.sort={key,dir:-1};
    renderTable();
  }));
  const ex=$("#export");if(ex)ex.addEventListener("click",()=>exportTable());
  /* a screen named in the URL is the page's question */
  const sc=new URLSearchParams(location.search).get("screen");
  if(sc&&SCREENS[sc])state.screen=sc;
  /* the filter chips and switches leave a screen: they are a different question */
  document.querySelectorAll("[data-min],#fchip,#hchip,#q").forEach(el=>el.addEventListener(el.id==="q"?"input":"click",()=>{if(state.screen){state.screen="";history.replaceState(null,"",location.pathname);}},true));
  renderTable();
}
state.sort={key:"val",dir:-1};state.q="";state.min=0;state.screen="";state.tbF=false;state.tbH=false;state.live={panel:false,hist:false,events:false,founders:false,prices:false};
boot();
