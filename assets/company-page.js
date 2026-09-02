/* ---------------- the company page ----------------
   Everything above this line was extracted from index.html at deploy (the
   declarations marked @shared). Below: what this page does with it. The shell
   carries the numbers a search engine and a card need; the shards carry
   the record; the seal decides who sees which. */
const C=window.COMPANY||{};
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");

function setRow(row){
  PANEL=[row];
  if(C.founder)FOUNDERS[row.tk]=C.founder;
  $("#cbadge").innerHTML=fBadge(row.tk);
  const fi=fInfo(row.tk);
  if(fi&&fi.f==="yes"&&fi.ev)
    $("#cquote").innerHTML=`<div class="cquote">“${esc(fi.ev.slice(0,320))}”<span class="src">${esc(fi.src||"the proxy statement")}</span></div>`;
}

function renderSealed(){
  $("#cbody").innerHTML=`<div class="cseal">
    <div class="p">${SEAL} This company's stake is behind the seal.</div>
    <div class="l">It is computed from its filings like every other, and sits in the Pro tier.
      The S&amp;P 500 is open to everyone; Pro is the other 1,635 companies — no lens a free
      reader lacks, only more companies. $5 a month, cancel in one click.</div>
    <a class="gopro" style="display:inline-block;text-decoration:none" href="/api/checkout">Go Pro — $5/month</a>
    <div class="l" style="margin-top:10px;font-size:13px">Already subscribed? <a href="/" style="color:var(--blue)">Sign in on the home page</a> and come back.</div>
  </div>`;
}

function stakeBlock(r){
  const pct=r.units?`<div class="p" style="font-size:28px;color:var(--ink)">Held as partnership units</div>
      <div class="l">This CEO's stake is structured as exchangeable partnership units rather than common stock, so a percent of common shares cannot describe it.</div>`
    :r.pct===null?`<div class="p" style="font-size:28px;color:var(--ink)">Not measured</div><div class="l">${esc(r.flags||"the walk could not settle on a figure")}</div>`
    :`<div class="p">${r.pct.toFixed(r.pct<1?3:2)}%</div>
      <div class="l">of common shares outstanding, per the newest Form 4 for each class${r.src13?` — from ${esc(r.src13)}`:""}. Computed from the filings, never estimated.</div>`;
  const st=(HIST[r.tk]&&HIST[r.tk].length>1)?trajStats(r.tk,1095):null;
  const sold=soldTickers();
  const last=lastTrade(r.tk);
  return `<div class="cstake">${pct}
    <div class="cstats">
      <div class="cstat"><div class="k">Shares held</div><div class="v">${r.sh!==null?fmt(r.sh):"—"}</div></div>
      <div class="cstat"><div class="k">Shares outstanding</div><div class="v">${r.out?fmt(r.out):"—"}</div></div>
      <div class="cstat"><div class="k">Stake value</div><div class="v">${r.val?money(r.val):"—"}</div></div>
      <div class="cstat"><div class="k">Close used</div><div class="v s">${r.price?("$"+r.price.toFixed(2)+" · "+(PRICES_ASOF||"")):"—"}</div></div>
      <div class="cstat"><div class="k">Holding as of</div><div class="v s">${r.asof||"—"}</div></div>
      <div class="cstat"><div class="k">Confidence</div><div class="v s"><span class="conf"><span class="dot ${r.conf}"></span>${r.conf}</span></div></div>
      <div class="cstat"><div class="k">3-year change</div><div class="v ${st&&st.d>0.05?"up":st&&st.d<-0.05?"down":""}">${st===null?"—":Math.abs(st.d)>100?"⚠":(st.d>=0?"+":"−")+Math.abs(st.d).toFixed(Math.abs(st.d)<1?2:1)+"%"}</div>
        ${st&&Math.abs(st.d)<=100?`<div class="k" style="text-transform:none;letter-spacing:0;margin-top:3px">${st.base.toFixed(2)}% on ${st.baseDate} → ${st.cur.toFixed(2)}% on ${st.curDate}</div>`:""}</div>
      <div class="cstat"><div class="k">Sales on record</div><div class="v s">${!HIST[r.tk]?"—":sold.has(r.tk)?"has reduced the stake":'<span style="color:#0b7a4b;font-weight:600">never sold</span>'}</div></div>
    </div>
    ${last?`<div class="cstat" style="border-bottom:0"><div class="k">Last trade that moved the stake</div>
      <div class="v s"><span class="abadge ${evBadge(last).k}">${evBadge(last).t}</span> &nbsp;${last.v&&!last.fl?money(last.v):compact(last.sh)+" sh"} · traded ${last.td||last.fd} · filed ${last.fd}</div></div>`:""}
  </div>`;
}

function lastTrade(tk){
  let best=null;
  for(const e of EVENTS){
    if(e.tk!==tk||unchangedKind(e)!==null||(e.c!=="P"&&e.c!=="S"))continue;
    if(!best||(e.td||e.fd)>(best.td||best.fd))best=e;
  }
  return best;
}

function recordBlock(r){
  const raw=HIST[r.tk];
  if(!raw||!raw.length)return `<div class="csec"><h2>Ownership over time</h2><div class="tnote">No record yet — this company has no walkable filing history.</div></div>`;
  const pts=cleanHist(r.tk);
  const left=raw.length-pts.length;
  return `<div class="csec"><h2>Ownership over time<small>${raw.length} transaction-days on record</small></h2>
    <div class="chartbox">${chartSVG(pts.length>1?pts:raw,{w:720,h:240})}</div>
    <div class="tnote">The stake after each filing, ${raw[0][0]} to ${raw[raw.length-1][0]}${left?` — ${left} point${left===1?"":"s"} left out where the record lied (a restated balance, or a stake above 100% while the share count lagged an issuance)`:""}.</div>
  </div>`;
}

function tradesBlock(r){
  const evs=EVENTS.filter(e=>e.tk===r.tk).sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||b.fd.localeCompare(a.fd));
  if(!evs.length)return `<div class="csec"><h2>Trades</h2><div class="tnote">No purchase or sale on record since 2016.</div></div>`;
  const kept=evs.filter(e=>unchangedKind(e)!==null).length;
  const rows=evs.map(e=>{
    const b=evBadge(e);const p=pctOf(e);const uk=unchangedKind(e);
    const stk=uk==="pre"?"pre-IPO":uk!==null?"stake unchanged":p?`${p.approx?"≈ ":""}${e.c==="P"?"+":"−"}${p.v>=100?"100%+":p.v.toFixed(p.v<1?2:1)+"%"} of stake`:"share of stake not stated";
    return `<div class="drow"><span class="adate" title="traded ${e.td||e.fd}; filed ${e.fd}${lagNote(e)}">${e.td||e.fd}</span>
      <span class="abadge ${b.k}" title="${esc(b.n)}">${b.t}</span>
      <span class="aval ${e.c==="P"?"up":"down"}">${evValCell(e)}</span>
      <span class="adlt ${e.c==="P"?"up":"down"}">${e.c==="P"?"+":"−"}${compact(e.sh)}</span>
      <span class="asub">${stk}${e.pl==="plan"?" · planned":e.pl==="discretionary"?" · discretionary":""}</span>
      ${e.u?`<a href="${e.u}" target="_blank" rel="noopener" title="the filing itself, on EDGAR">Form 4 ↗</a>`:""}
    </div>`}).join("");
  return `<div class="csec ctrades"><h2>Every trade since 2016<small>${evs.length} trade${evs.length===1?"":"s"}${kept?` · ${kept} kept apart`:""}</small></h2>${rows}
    <div class="tnote" style="margin-top:10px">Trades that did not move the public-company stake — options cashed, units converted, pre-IPO catch-ups — are listed and badged, and kept out of every summary.</div></div>`;
}

function reportBlock(r){
  const subj=encodeURIComponent(`${r.tk}: a figure looks wrong`);
  const body=encodeURIComponent(`Company: ${r.co} (${r.tk})\nWhat I see: \nWhat I think it should be: \nWhere I checked: \n\nPage: https://founderledequities.com/company/${r.tk}/`);
  return `Source: SEC EDGAR · figures are computed, never estimated. Prices, where shown, are the ${PRICES_ASOF||"latest"} close.
    If a number here looks wrong, <a href="mailto:hello@founderledequities.com?subject=${subj}&body=${body}">say so</a> — every figure links to the filing it came from, and corrections are made in the open.`;
}

function renderOpen(r){
  $("#cbody").innerHTML=`<div class="cgrid"><div>${stakeBlock(r)}</div><div>${recordBlock(r)}</div></div>${tradesBlock(r)}`;
  $("#creport").innerHTML=reportBlock(r);
}

async function fetchText(paths){
  for(const p of paths){
    try{const r=await fetch(p,{cache:"no-store"});if(r.ok)return await r.text();}catch(e){}
  }
  return null;
}

(async function main(){
  let pro=false;
  try{const r=await fetch("/api/me",{cache:"no-store"});if(r.ok){const j=await r.json();pro=!!j.pro;}}catch(e){}
  let row=C.row?mapPanel([C.row])[0]:null;
  if(!row&&pro){
    /* a sealed company for a subscriber: the row comes from the Pro universe */
    const t=await fetchText(["/pro/universe.csv"]);
    if(t){const p=mapPanel(parseCSV(t)).find(x=>x.tk===C.tk);if(p)row=p;}
  }
  if(!row){setRow({tk:C.tk,co:C.co,ceo:C.ceo,pct:null,sh:null,out:null,asof:"",conf:"medium"});renderSealed();return;}
  if(C.price){row.price=C.price;row.val=row.sh?row.sh*C.price:null;PRICES_ASOF=C.price_date||"";}
  setRow(row);
  renderOpen(row);   /* the numbers first; the record and trades fill in */
  const base=(C.sp||!pro)?"":"/pro";
  const [h,e]=await Promise.all([
    fetchText([`${base}/history/${C.tk}.csv`,`/history/${C.tk}.csv`]),
    fetchText([`${base}/events/${C.tk}.csv`,`/events/${C.tk}.csv`])]);
  if(h){const m=mapHistory(parseCSV(h));if(m[C.tk])HIST=m;}
  if(e){EVENTS=mapEvents(parseCSV(e)).filter(x=>x.tk===C.tk);}
  renderOpen(row);
})();
