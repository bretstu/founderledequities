/* ---------------- the company page ----------------
   Everything above this line was extracted from index.html at deploy (the
   declarations marked @shared). Below: what this page does with it. */
const C=window.COMPANY||{};
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
let VIEW="all";

function nav(me){
  /* one button, two lives, on this page too */
  const b=document.querySelector(".topnav .gopro");if(!b)return;
  if(me&&me.pro){b.textContent="Account";b.setAttribute("href","/api/portal");b.title="Manage your subscription";}
}

function setRow(row){
  PANEL=[row];
  if(C.founder)FOUNDERS[row.tk]=C.founder;
  $("#cbadge").innerHTML=fBadge(row.tk);
}

function renderSealed(){
  $("#cbody").innerHTML=`<div class="cseal">
    <div class="p">${SEAL} This company's stake is in the Pro tier.</div>
    <div class="l">It is computed from its filings like every other. The S&amp;P 500 is open to everyone;
      Pro is the other 1,635 companies — no lens a free reader lacks, only more companies. $5 a month, cancel in one click.</div>
    <a class="gopro" style="display:inline-block;text-decoration:none" href="/api/checkout">Go Pro — $5/month</a>
    <div class="l" style="margin-top:10px;font-size:13px">Already subscribed? <a href="/" style="color:var(--blue)">Sign in on the home page</a> and come back.</div>
  </div>`;
  $("#creport").innerHTML=reportBlock({tk:C.tk,co:C.co});
}

/* ---- the answer band ---- */
function band(r){
  const st=(HIST[r.tk]&&HIST[r.tk].length>1)?trajStats(r.tk,1095):null;
  const mcap=r.price&&r.out?r.out*r.price:null;
  const big=r.units?`<div class="p s">Held as partnership units</div><div class="pl">Exchangeable units rather than common stock, so a percent of common shares cannot describe the stake.</div>`
    :r.pct===null?`<div class="p s">Not measured</div><div class="pl">${esc(r.flags||"the record could not settle on a figure")}</div>`
    :`<h2 class="p"><span class="vh">${esc(C.ceo)} owns </span>${r.pct.toFixed(r.pct<1?3:2)}%<span class="vh"> of ${esc(C.co)}</span></h2><div class="pl">of ${esc(C.co)}'s common shares, computed from the filings — never estimated${r.tabled!==null&&r.out?`<br><span title="${esc((r.flags||"").split("\n").find(f=>/in a remark/.test(f))||"")}">${(100*r.tabled/r.out).toFixed(2)}% of it is in the filing tables; the rest is stated in a remark and counted here</span>`:""}</div>`;
  const chg=st===null?`<div class="v">—</div><div class="s">no three-year record</div>`
    :Math.abs(st.d)>100?`<div class="v">⚠</div><div class="s">the record's three-year point is not reconciled</div>`
    :`<div class="v ${st.d>0.05?"up":st.d<-0.05?"down":""}">${(st.d>=0?"+":"−")+Math.abs(st.d).toFixed(Math.abs(st.d)<1?2:1)}%</div><div class="s">${st.base.toFixed(2)}% → ${st.cur.toFixed(2)}% since ${st.baseDate.slice(0,7)}</div>`;
  return `<div class="cband">
    <div>${big}</div>
    <div class="cstat"><div class="k">Stake value</div><div class="v">${r.val?money(r.val):"—"}</div><div class="s">${r.price?"at $"+r.price.toFixed(2)+" · "+(PRICES_ASOF||"latest close"):"no close on file"}</div></div>
    <div class="cstat"><div class="k">Market cap</div><div class="v">${mcap?money(mcap):"—"}</div><div class="s">${r.out?fmt(r.out)+" shares outstanding":""}</div></div>
    <div class="cstat"><div class="k">Shares held</div><div class="v">${r.sh!==null?compact(r.sh):"—"}</div><div class="s">${r.sh!==null?fmt(r.sh):""}${r.tabled!==null&&r.sh!==null&&r.out?`<br>${fmt(r.tabled)} in the filing tables (${(100*r.tabled/r.out).toFixed(2)}%); the rest disclosed in a remark`:""}</div></div>
    <div class="cstat"><div class="k">3-year change</div>${chg}</div>
  </div>
  <div class="cmeta">
    <span>holding as of ${r.asof||"—"}${r.form4?` · <a href="${r.form4}" target="_blank" rel="noopener" style="color:var(--blue);text-decoration:none">the filing ↗</a>`:""}</span>
    <span class="conf" title="how well the newest filing reconciles with the record">confidence: ${r.conf}</span>
  </div>`;
}

/* ---- the record: the stake over time, with the trades on the line ---- */
/* ONE POINT PER MONTH-END. The record steps at every filing and every
   cover-page count; at a ten-year scale that is a staircase of same-week
   moves that means nothing and looks like noise. Each month keeps its last
   point, and remembers why the month moved: a trade, a grant, a gift, tax
   withholding, options exercised, or the share count changing with no
   change in the holding. Trades keep their exact dates as dots. */
const CODE_WORDS={P:"bought",S:"sold",A:"granted",G:"gift",F:"tax withholding",M:"options exercised",C:"converted",D:"returned to the company",J:"other",X:"options exercised"};
function monthEnds(pts){
  const out=[];let cur=null;
  for(const p of pts){
    const m=p[0].slice(0,7);
    if(!cur||cur.m!==m){if(cur)out.push(cur);cur={m,pt:p,codes:new Set()};}
    else cur.pt=p;
    for(const c of (p[3]||""))if(CODE_WORDS[c])cur.codes.add(c);
  }
  if(cur)out.push(cur);
  const series=[];
  for(let i=0;i<out.length;i++){
    const o=out[i],prev=series[i-1];
    const dS=prev?o.pt[2]-prev.sh:0,dP=prev?o.pt[1]-prev.pct:0;
    const why=[];
    for(const c of o.codes)why.push(CODE_WORDS[c]);
    if(prev&&Math.abs(dS)<1&&Math.abs(dP)>1e-6)why.push("share count changed");
    if(prev&&Math.abs(dS)>=1&&!o.codes.size)why.push(dS>0?"shares added":"shares removed");
    series.push({d:o.pt[0],m:o.m,pct:o.pt[1],sh:o.pt[2],why:why.join(", "),dP,dS});
  }
  return series;
}
function monthLabel(m){const [y,mo]=m.split("-");return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mo-1]+" "+y;}
function compactD(n,dec){
  const a=Math.abs(n);
  for(const [div,suf] of [[1e12,"T"],[1e9,"B"],[1e6,"M"],[1e3,"K"]])if(a>=div)return (n/div).toFixed(dec)+suf;
  return Math.round(n).toLocaleString("en-US");
}
function stakeChart(pts,evs,{w=940,h=300,mode="pct"}={}){
  const pad={l:64,r:22,t:18,b:30};
  const ms=monthEnds(pts);if(ms.length<2)return "";
  const val=o=>mode==="shares"?o.sh:o.pct;
  const t0=Date.parse(ms[0].d),t1=Date.parse(ms[ms.length-1].d)||t0+1;
  let lo=Infinity,hi=-Infinity;for(const o of ms){const v=val(o);if(v<lo)lo=v;if(v>hi)hi=v;}
  let span=hi-lo;
  if(span<=Math.abs(hi)*1e-6){/* a flat record (never traded, never diluted): a ±2% band, not a line on a hairline */
    lo=hi*0.98;hi=hi*1.02;span=hi-lo;}
  else{lo=Math.max(0,lo-span*0.12);hi=hi+span*0.12;}
  const X=d=>pad.l+(Date.parse(d)-t0)/((t1-t0)||1)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
  /* axis labels must differ: a narrow range gets more digits, not four copies of one */
  const ticks=[0,1,2,3].map(k=>lo+(hi-lo)*k/3);
  const fmtAt=dec=>v=>mode==="shares"?compactD(v,dec):v.toFixed(dec)+"%";
  let dec=mode==="shares"?2:(hi<10?2:1);
  while(dec<4&&new Set(ticks.map(fmtAt(dec))).size<ticks.length)dec++;
  const fmt=fmtAt(dec);
  /* a step line: the value holds between month-ends */
  let d="";ms.forEach((o,i)=>{const x=X(o.d),y=Y(val(o));d+=i?` H ${x.toFixed(1)} V ${y.toFixed(1)}`:`M ${x.toFixed(1)} ${y.toFixed(1)}`;});
  const last=[ms[ms.length-1].d,val(ms[ms.length-1])];
  const first=[ms[0].d,val(ms[0])];
  const area=d+` V ${(h-pad.b).toFixed(1)} H ${X(first[0]).toFixed(1)} Z`;
  let out=`<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${mode==="shares"?"shares held over time":"the stake over time"}">`;
  /* the axis: four gridlines */
  for(let k=0;k<=3;k++){const v=lo+(hi-lo)*k/3;const y=Y(v);
    out+=`<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w-pad.r}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out+=`<text x="${pad.l-8}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="10.5" fill="var(--faint)">${fmt(v)}</text>`;}
  /* years along the bottom */
  const y0=new Date(t0).getUTCFullYear(),y1=new Date(t1).getUTCFullYear();
  for(let yr=y0+1;yr<=y1;yr++){const x=X(`${yr}-01-01`);if(x<pad.l||x>w-pad.r)continue;
    out+=`<text x="${x.toFixed(1)}" y="${h-10}" text-anchor="middle" font-family="var(--mono)" font-size="10.5" fill="var(--faint)">${yr}</text>`;}
  out+=`<path d="${area}" fill="var(--blue)" opacity="0.06"/>`;
  out+=`<path d="${d}" fill="none" stroke="var(--blue)" stroke-width="1.8" stroke-linejoin="round"/>`;
  /* EVERY STEP EXPLAINS ITSELF ON HOVER: one invisible band per month,
     titled with the value and why it moved. */
  for(let i=0;i<ms.length;i++){
    const o=ms[i];const x0=X(o.d),x1=i+1<ms.length?X(ms[i+1].d):w-pad.r;
    const move=i?(mode==="shares"?(o.dS?`${o.dS>0?"+":"−"}${compact(Math.abs(o.dS))} sh`:"no change"):(Math.abs(o.dP)>1e-6?`${o.dP>0?"+":"−"}${Math.abs(o.dP).toFixed(2)} pts`:"no change")):"start";
    const why=o.why?` · ${o.why}`:"";
    out+=`<rect x="${x0.toFixed(1)}" y="${pad.t}" width="${Math.max(1,x1-x0).toFixed(1)}" height="${(h-pad.t-pad.b).toFixed(1)}" fill="transparent"><title>${monthLabel(o.m)} · ${o.pct.toFixed(2)}% · ${compact(o.sh)} sh · ${move}${why}</title></rect>`;
  }
  /* the trades, on the line at their trade date, sized by value */
  const at=dt=>{let v=val(ms[0]);for(const o of ms){if(o.d<=dt)v=val(o);else break;}return v;};
  const vmax=Math.max(1,...evs.map(e=>e.v||0));
  for(const e of evs){
    const dt=e.td||e.fd;if(dt<pts[0][0]||dt>last[0])continue;
    const x=X(dt),y=Y(at(dt));const rr=3+5*Math.sqrt((e.v||0)/vmax);
    const buy=e.c==="P";
    out+=`<a href="${e.u||"#"}" target="_blank" rel="noopener"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${rr.toFixed(1)}" fill="${buy?"var(--blue)":"#c22a2a"}" fill-opacity="0.85" stroke="#fff" stroke-width="1.2"><title>${buy?"Bought":"Sold"} ${e.v?money(e.v):compact(e.sh)+" sh"} · ${dt}${e.pl==="plan"?" · planned":e.pl==="discretionary"?" · discretionary":""}</title></circle></a>`;
  }
  out+=`<text x="${(X(last[0])-6).toFixed(1)}" y="${(Y(last[1])-9).toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="11" font-weight="600" fill="var(--blue)">${fmt(last[1])}</text>`;
  out+=`</svg>`;
  return out;
}
function recordBlock(r){
  const raw=HIST[r.tk];
  if(!raw||!raw.length)return `<div class="csec"><h2>The stake over time</h2><div class="sub">No record yet — this company has no walkable filing history.</div></div>`;
  const pts=cleanHist(r.tk);const left=raw.length-pts.length;
  const moving=EVENTS.filter(e=>e.tk===r.tk&&unchangedKind(e)===null&&(e.c==="P"||e.c==="S"));
  const buys=moving.filter(e=>e.c==="P"),sells=moving.filter(e=>e.c==="S");
  const sum=a=>a.reduce((t,e)=>t+((e.fl?0:e.v)||0),0);
  const series=pts.length>1?pts:raw;
  const mode=window._chartMode||"pct";
  return `<div class="csec"><div class="chead"><h2>${mode==="shares"?"Shares held over time":"The stake over time"}</h2>
    <div class="chips" role="group" aria-label="chart view">
      <button class="chip${mode==="pct"?" on":""}" onclick="setChartMode('pct')" title="the share of the company: moves when the holding changes and when the share count changes">% of company</button>
      <button class="chip${mode==="shares"?" on":""}" onclick="setChartMode('shares')" title="the shares held, split-adjusted: moves only when the person buys, sells, is granted, gifts, or forfeits shares; flat while the company dilutes">Shares held</button>
    </div></div>
    <div class="sub">${series[0][0].slice(0,4)} to ${series[series.length-1][0]}, one point per month-end${left?` — ${left} point${left===1?"":"s"} left out where the record lied`:""}.
      ${moving.length?` Since 2016: <b>${buys.length?`bought ${money(sum(buys))} in ${buys.length} trade${buys.length===1?"":"s"}`:"no purchases"}</b>, <b>${sells.length?`sold ${money(sum(sells))} in ${sells.length}`:"no sales"}</b>.`:""}</div>
    <div class="cchart">${stakeChart(series,moving,{mode})}</div>
    <div class="ckey">${moving.length?`<span class="b"><i></i>bought</span><span class="s"><i></i>sold</span><span>· dot size follows the trade's value · click a dot for the filing ·</span>`:""}<span>${mode==="shares"?"steps without a dot are grants, gifts, tax withholding or options exercised":"steps without a dot are grants, gifts, or the share count changing"} · hover the line for the month</span></div>
  </div>`;
}

/* ---- the trades ---- */
function tradesBlock(r){
  const all=EVENTS.filter(e=>e.tk===r.tk).sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||b.fd.localeCompare(a.fd));
  if(!all.length)return `<div class="csec"><h2>Every trade since 2016</h2><div class="sub">No purchase or sale on record.</div></div>`;
  const kept=all.filter(e=>unchangedKind(e)!==null);
  const evs=VIEW==="all"?all:VIEW==="buys"?all.filter(e=>e.c==="P"&&unchangedKind(e)===null):VIEW==="sells"?all.filter(e=>e.c==="S"&&unchangedKind(e)===null):kept;
  const chip=(v,lab,n)=>`<button class="chip${VIEW===v?" on":""}" onclick="VIEW='${v}';renderOpen(PANEL[0])">${lab} <small>${n}</small></button>`;
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
  return `<div class="csec ctrades"><h2>Every trade since 2016</h2>
    <div class="tchips">${chip("all","All",all.length)}${chip("buys","Bought",all.filter(e=>e.c==="P"&&unchangedKind(e)===null).length)}${chip("sells","Sold",all.filter(e=>e.c==="S"&&unchangedKind(e)===null).length)}${chip("kept","Kept apart",kept.length)}</div>
    ${rows||`<div class="sub">Nothing in this view.</div>`}
    ${VIEW==="kept"?`<div class="sub" style="margin-top:10px">Kept apart: options cashed, units converted, pre-IPO catch-ups — real trades that did not move the public-company stake, listed and badged, left out of every summary.</div>`:""}
  </div>`;
}

/* ---- the receipt for the badge ---- */
function whyBlock(r){
  const fi=fInfo(r.tk);if(!fi||!fi.ev)return"";
  /* whole sentences only: trim the window to its first and last full stop */
  let ev=fi.ev.replace(/\s+/g," ").trim();
  const i=ev.search(/[.!?]\s+[A-Z]/);if(i>0&&i<ev.length-40&&!/^[A-Z]/.test(ev))ev=ev.slice(i+1).trim();
  const j=ev.lastIndexOf(".");if(j>40)ev=ev.slice(0,j+1);
  const verdict=fi.f==="yes"?"Named a founder":fi.f==="no"?"Not a founder":"Founder status unclear";
  const src=(fi.src||"").trim();const m=src.match(/(\d{10}-\d{2}-\d{6})/);
  const link=m&&r.cik?`https://www.sec.gov/Archives/edgar/data/${r.cik}/${m[1].replace(/-/g,"")}/`:"";
  return `<div class="cwhy"><div class="k">Why the badge</div>
    <b style="color:var(--ink)">${verdict}</b> — the proxy statement says: <q>${esc(ev)}</q>
    <span class="src">${link?`<a href="${link}" target="_blank" rel="noopener">${esc(src)} ↗</a>`:esc(src||"the proxy statement")}</span></div>`;
}

function reportBlock(r){
  const subj=encodeURIComponent(`${r.tk}: a figure looks wrong`);
  const body=encodeURIComponent(`Company: ${r.co} (${r.tk})\nWhat I see: \nWhat I think it should be: \nWhere I checked: \n\nPage: https://founderledequities.com/company/${r.tk}/`);
  return `Source: SEC EDGAR · figures are computed, never estimated. Prices, where shown, are the ${PRICES_ASOF||"latest"} close.
    If a number here looks wrong, <a href="mailto:hello@founderledequities.com?subject=${subj}&body=${body}">say so</a> — every figure links to the filing it came from, and corrections are made in the open.`;
}

function renderOpen(r){
  window._lastRow=r;
  $("#cbody").innerHTML=band(r)+recordBlock(r)+tradesBlock(r)+whyBlock(r);
  $("#creport").innerHTML=reportBlock(r);
}

async function fetchText(paths){
  for(const p of paths){try{const q=await fetch(p,{cache:"no-store"});if(q.ok)return await q.text();}catch(e){}}
  return null;
}

(async function main(){
  let me=null;
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)me=await q.json();}catch(e){}
  nav(me);
  const pro=!!(me&&me.pro);
  let row=C.row?mapPanel([C.row])[0]:null;
  if(!row&&pro){
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

function setChartMode(m){window._chartMode=m;if(window._lastRow)renderOpen(window._lastRow);}
