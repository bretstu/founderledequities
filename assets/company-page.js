/* ---------------- the company page ----------------
   Everything above this line was extracted from index.html at deploy (the
   declarations marked @shared). Below: what this page does with it. */
const C=window.COMPANY||{};
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
let VIEW="all",BIG=false;   /* BIG: only rows that moved the stake by 1% or more */

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

/* whose stake: "Elon Musk's", "Jabbok Schlacks'" */
const poss=n=>n+(/s$/i.test(n)?"'":"'s");

function renderSealed(){
  $("#cbody").innerHTML=`<div class="cseal">
    <div class="k" style="font-family:var(--mono);font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--blue)">${esc(poss(C.ceo||"The chief executive"))} stake</div>
    <h2 class="p s">is in Pro</h2>
    <div class="l">Computed from the filings like every other. Pro is every company beyond the S&amp;P 500: the stake, the record, every trade. $5 a month, cancel in one click.</div>
    <a class="gopro" href="/api/checkout">Go Pro, $5/month</a>
    <div class="l" style="font-size:13px">Already subscribed? <a href="/" style="color:var(--blue)">Sign in on the home page</a> and come back.</div>
  </div>`;
  $("#creport").innerHTML=reportBlock({tk:C.tk,co:C.co});
}

/* ---- the answer band: five cards ----
   THE LABELS ARE THE TABLE'S. Value, Market cap, 1Y return: the words the
   home page uses for the same numbers, computed the same way (shares x
   close; outstanding x close; the store's twelve-month price return).
   Nothing here is explained in a sentence; a figure that needed one has
   been taken off the page. The stake's own trajectory is the Stake
   chart's job, not a "3-year change" card that had to say "since 2026-01"
   when the record was eight months old. */
function stat(k,v,cls,sub,title){return `<div class="cstat"${title?` title="${esc(title)}"`:""}><div class="k">${k}</div><div class="v ${cls||""}">${v}</div>${sub?`<div class="s">${sub}</div>`:""}</div>`;}
function band(r){
  const mcap=r.price&&r.out?r.out*r.price:null;
  /* the card reads as one sentence around the number: MARK ZUCKERBERG
     OWNS / 13.44% / of Meta Platforms, Inc. */
  const who=`<div class="k">${esc(C.ceo||"The chief executive")} ${r.units||r.pct===null?"holds":"owns"}</div>`;
  const big=r.units?`${who}<div class="p s">partnership units</div><div class="pl">Exchangeable units rather than common stock, so a percent of common shares cannot describe the stake.</div>`
    :r.pct===null?`${who}<div class="p s">a stake not measured</div><div class="pl">${esc(r.flags||"the record could not settle on a figure")}</div>`
    :`${who}<h2 class="p">${r.pct.toFixed(r.pct<1?3:2)}%</h2>`;
  const asof=PRICES_ASOF||"latest";
  const tabled=r.tabled!==null&&r.sh!==null&&r.out?`${fmt(r.tabled)} in the filing tables; the rest stated in a remark`:"";
  /* THREE CARDS, ONE SUBJECT. The page is about what this person owns of
     this company: the share, the shares, and what they are worth. Market
     cap, price and the year's return are facts about the stock, context
     for the stake and not the answer, so they sit in the kicker line with
     the ticker and the tier, in that line's small mono register. */
  /* the ticker and the market cap beside the name */
  const kick=$("#ctk");
  if(kick)kick.innerHTML=`${esc(r.tk)}${mcap?` · ${money(mcap)}`:""}`;
  /* where the stake stood when the record began, against today */
  const rec=cleanHist(r.tk);
  const first=rec.length?rec[0]:null;
  const since=first&&r.pct!==null?stat("Since "+first[0].slice(0,4),`${first[1].toFixed(first[1]<1?2:1)}% → ${r.pct.toFixed(r.pct<1?2:1)}%`,"since","",`the stake at the record's first point, ${first[0]}, and today`)
    :stat("Since 2016","&mdash;","none","","the record has no earlier point");
  return `<div class="cband five">
    <div>${big}</div>
    ${stat("Shares held",r.sh!==null?fmt(r.sh):"&mdash;","",tabled,"shares held, per the latest filing")}
    ${stat("Outstanding",r.out?fmt(r.out):"&mdash;","","",`shares outstanding${r.oasof?`, per the ${dayLabel(r.oasof)} cover page`:""}: the denominator of the percent`)}
    ${stat("Worth",r.val?money(r.val):"&mdash;","","",`the stake's value: shares held at the ${asof} close${r.price?` of $${r.price.toFixed(2)}`:""}`)}
    ${since}
  </div>`;
}

/* ---- the record: the price and the stake, with the trades on the line ----
   ONE POINT PER MONTH-END for the stake. The record steps at every filing
   and every cover-page count; at a ten-year scale that is a staircase of
   same-week moves that means nothing and looks like noise. Each month keeps
   its last point, and remembers why the month moved: a trade, a grant, a
   gift, tax withholding, options exercised, or the share count changing
   with no change in the holding. Trades keep their exact dates as dots.

   THE PRICE CHART answers the question a reader actually has about an
   insider: did they sell into a top, did they buy the crash. Daily closes,
   split-adjusted, from the price store; every dot sits at the price ON THE
   FILING, restated in today's shares, so the gap between a dot and the
   line is itself information. Grants, gifts and withholding are not
   decisions about price and are not drawn.

   The line draws in once on load. Hover is a crosshair with the day and
   the nearest trade, not the browser's grey tooltip. */
let PRICES_DAILY=null;   /* [[date, close], ...] for this ticker, or null */
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
function dayLabel(d){return monthLabel(d.slice(0,7)).replace(" ",` ${+d.slice(8,10)}, `);}
const dollars=v=>Math.abs(v-Math.round(v))<1e-9&&v>=1?"$"+Math.round(v).toLocaleString("en-US"):v>=1000?"$"+Math.round(v).toLocaleString("en-US"):v>=100?"$"+v.toFixed(0):v>=10?"$"+v.toFixed(1):"$"+v.toFixed(2);
/* the frame: narrow screens get a taller box so the line has room */
function frame(){const narrow=(window.innerWidth||1000)<600;return narrow?{w:520,h:340,pad:{l:54,r:16,t:26,b:30}}:{w:940,h:320,pad:{l:64,r:22,t:26,b:30}};}
const SELL="#c22a2a";
/* the dots, shared by both charts: sized by value, a white rim so
   neighbours stay distinct. Hover says what the trade was; the list
   below the chart carries the filing link. */
function dots(evs,X,Y,at,fr){
  const drawn=evs.slice().sort((a,b)=>(b.v||0)-(a.v||0));
  const vmax=Math.max(1,...drawn.map(e=>e.v||0));
  let out="";
  drawn.forEach((e,i)=>{
    const dt=e.td||e.fd;const [y,note]=at(e);const x=X(dt),yy=Y(y);
    const rr=3+5*Math.sqrt((e.v||0)/vmax);const buy=e.c==="P";const col=buy?"var(--buy)":SELL;
    out+=`<circle class="dot" style="--i:${Math.min(i,40)}" cx="${x.toFixed(1)}" cy="${yy.toFixed(1)}" r="${rr.toFixed(1)}" fill="${col}" fill-opacity="0.85" stroke="#fff" stroke-width="1.2"><title>${buy?"Bought":"Sold"} ${e.v?money(e.v):compact(e.sh)+" sh"} · ${compact(e.sh)} sh${note} · ${dt}${e.pl==="plan"?" · planned":e.pl==="discretionary"?" · discretionary":""}</title></circle>`;
  });
  return out;
}
function yearsAxis(X,t0,t1,fr){
  let out="";const y0=new Date(t0).getUTCFullYear(),y1=new Date(t1).getUTCFullYear();
  const every=(y1-y0)>7&&fr.w<600?2:1;
  for(let yr=y0+1;yr<=y1;yr++){if((yr-y0)%every)continue;const x=X(`${yr}-01-01`);if(x<fr.pad.l||x>fr.w-fr.pad.r)continue;
    out+=`<text x="${x.toFixed(1)}" y="${fr.h-10}" text-anchor="middle" font-family="var(--mono)" font-size="10.5" fill="var(--faint)">${yr}</text>`;}
  return out;
}
/* the hover's data rides on the svg: one row per x-position the cursor can
   land on, [date, label lines...], plus the frame it was drawn in */
function hoverAttrs(rows,fr,t0,t1){
  return `data-t0="${t0}" data-t1="${t1}" data-l="${fr.pad.l}" data-r="${fr.pad.r}" data-w="${fr.w}" data-t="${fr.pad.t}" data-b="${fr.pad.b}" data-h="${fr.h}" data-rows="${esc(JSON.stringify(rows))}"`;
}
function priceChart(px,evs){
  const fr=frame(),{w,h,pad}=fr;
  if(!px||px.length<2)return "";
  const t0=Date.parse(px[0][0]),t1=Date.parse(px[px.length-1][0])||t0+1;
  /* only the trades inside the price record shape the axis; a 2016 sale
     restated to $14 must not drag a $100 to $500 chart down to $20 */
  const drawn=evs.filter(e=>{const dt=e.td||e.fd;return dt>=px[0][0]&&dt<=px[px.length-1][0];});
  /* LOG SCALE. A stock up 10x over five years is a flat line for four of
     them on a linear axis, and every early trade sits in the mud. */
  let lo=Infinity,hi=-Infinity;for(const p of px){if(p[1]<lo)lo=p[1];if(p[1]>hi)hi=p[1];}
  for(const e of drawn){const y=e.apa||null;if(y&&y>0){if(y<lo)lo=y;if(y>hi)hi=y;}}
  lo=Math.max(lo,1e-3);
  const L0=Math.log(lo)-(Math.log(hi)-Math.log(lo))*0.08,L1=Math.log(hi)+(Math.log(hi)-Math.log(lo))*0.12;
  const X=d=>pad.l+(Date.parse(d)-t0)/((t1-t0)||1)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(Math.log(v)-L0)/((L1-L0)||1)*(h-pad.t-pad.b);
  const ticks=[];
  for(let e=Math.floor(Math.log10(lo))-1;e<=Math.ceil(Math.log10(hi));e++)for(const m of [1,1.5,2,3,5,7]){const v=m*Math.pow(10,e);if(Math.log(v)>L0&&Math.log(v)<L1)ticks.push(v);}
  while(ticks.length>5){for(let i=ticks.length-2;i>=0;i-=2)ticks.splice(i,1);}
  /* the line: one point per trading day, thinned to the pixel */
  let d="",lastX=-9;const hover=[];
  for(const p of px){const x=X(p[0]);if(x-lastX<0.7&&d)continue;lastX=x;d+=(d?" L ":"M ")+x.toFixed(1)+" "+Y(p[1]).toFixed(1);}
  /* the trades nearest each day, for the crosshair */
  const byDay={};for(const e of drawn){const dt=e.td||e.fd;(byDay[dt]=byDay[dt]||[]).push(e);}
  for(const p of px){const tr=byDay[p[0]];let line2="";
    if(tr){const b=tr.filter(e=>e.c==="P"),sl=tr.filter(e=>e.c==="S");const sum=a=>a.reduce((t,e)=>t+(e.v||0),0);
      line2=[b.length?`bought ${money(sum(b))}`:"",sl.length?`sold ${money(sum(sl))}`:""].filter(Boolean).join(", ");}
    hover.push([p[0],dayLabel(p[0])+" · "+dollars(p[1]),line2]);}
  let out=`<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="the share price, with the chief executive's trades on it" class="fchart" ${hoverAttrs(hover,fr,t0,t1)}>
  <defs><linearGradient id="pxg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity="0.16"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient>
  <clipPath id="pxc"><rect class="reveal" x="0" y="0" width="${w}" height="${h}"/></clipPath></defs>`;
  for(const v of ticks){const y=Y(v);
    out+=`<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w-pad.r}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out+=`<text x="${pad.l-8}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="10.5" fill="var(--faint)">${dollars(v)}</text>`;}
  out+=yearsAxis(X,t0,t1,fr);
  out+=`<path class="fill" clip-path="url(#pxc)" d="${d} V ${(h-pad.b).toFixed(1)} H ${X(px[0][0]).toFixed(1)} Z" fill="url(#pxg)"/>`;
  out+=`<path class="line" d="${d}" fill="none" stroke="var(--ink)" stroke-opacity="0.8" stroke-width="1.2" stroke-linejoin="round"/>`;
  const closeAt=dt=>{let v=px[0][1];for(const p of px){if(p[0]<=dt)v=p[1];else break;}return v;};
  out+=dots(drawn,X,Y,e=>{const dt=e.td||e.fd;return e.apa>0?[e.apa,` at ${dollars(e.apa)}${e.ap&&Math.abs(e.ap-e.apa)>0.005?` (filed at ${dollars(e.ap)}, before splits)`:""}`]:[closeAt(dt),` at the ${dollars(closeAt(dt))} close (price on the filing not restated)`];},fr);
  const last=px[px.length-1];
  /* the last close, labelled above its point; when the point sits in the
     top of the range the label would cross the line's peak, so it goes
     below instead (Schmitz's $20.1 on a chart topping at $20) */
  const ly=Y(last[1])-9<pad.t+12?Y(last[1])+16:Y(last[1])-9;
  out+=`<text class="endlbl" x="${(X(last[0])-6).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="11" font-weight="600" fill="var(--ink)">${dollars(last[1])}</text>`;
  out+=`<g class="xh" style="display:none"><line y1="${pad.t}" y2="${h-pad.b}" stroke="var(--ink)" stroke-opacity="0.35" stroke-dasharray="2 3"/><circle r="3.5" fill="var(--ink)"/><rect rx="3" fill="var(--ink)"/><text font-family="var(--mono)" font-size="10.5" fill="#fff"></text><text font-family="var(--mono)" font-size="10.5" fill="#fff"></text></g></svg>`;
  return out;
}
function stakeChart(pts,evs){
  const fr=frame(),{w,h,pad}=fr;
  const ms=monthEnds(pts);if(ms.length<2)return "";
  const t0=Date.parse(ms[0].d),t1=Date.parse(ms[ms.length-1].d)||t0+1;
  let lo=Infinity,hi=-Infinity;for(const o of ms){if(o.pct<lo)lo=o.pct;if(o.pct>hi)hi=o.pct;}
  let span=hi-lo;
  if(span<=Math.abs(hi)*1e-6){lo=hi*0.98;hi=hi*1.02;span=hi-lo;}   /* a flat record: a band, not a hairline */
  else{lo=Math.max(0,lo-span*0.12);hi=hi+span*0.14;}
  const X=d=>pad.l+(Date.parse(d)-t0)/((t1-t0)||1)*(w-pad.l-pad.r);
  const Y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
  const ticks=[0,1,2,3].map(k=>lo+(hi-lo)*k/3);
  let dec=hi<10?2:1;const fmtAt=dc=>v=>v.toFixed(dc)+"%";
  while(dec<4&&new Set(ticks.map(fmtAt(dec))).size<ticks.length)dec++;
  const fmt=fmtAt(dec);
  let d="";ms.forEach((o,i)=>{const x=X(o.d),y=Y(o.pct);d+=i?` H ${x.toFixed(1)} V ${y.toFixed(1)}`:`M ${x.toFixed(1)} ${y.toFixed(1)}`;});
  const hover=ms.map((o,i)=>{const move=i?(Math.abs(o.dP)>1e-6?`${o.dP>0?"+":"−"}${Math.abs(o.dP).toFixed(2)} pts`:"no change"):"start";
    return [o.d,`${monthLabel(o.m)} · ${o.pct.toFixed(2)}% · ${compact(o.sh)} sh`,`${move}${o.why?" · "+o.why:""}`];});
  let out=`<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="the stake over time" class="fchart" ${hoverAttrs(hover,fr,t0,t1)}>
  <defs><linearGradient id="stg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity="0.16"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient>
  <clipPath id="stc"><rect class="reveal" x="0" y="0" width="${w}" height="${h}"/></clipPath></defs>`;
  for(let k=0;k<=3;k++){const v=lo+(hi-lo)*k/3;const y=Y(v);
    out+=`<line x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w-pad.r}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out+=`<text x="${pad.l-8}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="10.5" fill="var(--faint)">${fmt(v)}</text>`;}
  out+=yearsAxis(X,t0,t1,fr);
  out+=`<path class="fill" clip-path="url(#stc)" d="${d} V ${(h-pad.b).toFixed(1)} H ${X(ms[0].d).toFixed(1)} Z" fill="url(#stg)"/>`;
  out+=`<path class="line" d="${d}" fill="none" stroke="var(--blue)" stroke-width="1.8" stroke-linejoin="round"/>`;
  const at=dt=>{let v=ms[0].pct;for(const o of ms){if(o.d<=dt)v=o.pct;else break;}return v;};
  const drawn=evs.filter(e=>{const dt=e.td||e.fd;return dt>=pts[0][0]&&dt<=ms[ms.length-1].d;});
  out+=dots(drawn,X,Y,e=>[at(e.td||e.fd),""],fr);
  const lastO=ms[ms.length-1];
  const lyO=Y(lastO.pct)-9<pad.t+12?Y(lastO.pct)+16:Y(lastO.pct)-9;
  out+=`<text class="endlbl" x="${(X(lastO.d)-6).toFixed(1)}" y="${lyO.toFixed(1)}" text-anchor="end" font-family="var(--mono)" font-size="11" font-weight="600" fill="var(--blue)">${fmt(lastO.pct)}</text>`;
  out+=`<g class="xh" style="display:none"><line y1="${pad.t}" y2="${h-pad.b}" stroke="var(--ink)" stroke-opacity="0.35" stroke-dasharray="2 3"/><circle r="3.5" fill="var(--blue)"/><rect rx="3" fill="var(--ink)"/><text font-family="var(--mono)" font-size="10.5" fill="#fff"></text><text font-family="var(--mono)" font-size="10.5" fill="#fff"></text></g></svg>`;
  return out;
}
/* THE CROSSHAIR. One handler for both charts: the cursor's x becomes a
   date, the nearest row supplies the label, the box stays inside the
   frame. Touch works the same way. */
function attachHover(svg){
  const rows=JSON.parse(svg.getAttribute("data-rows")||"[]");if(!rows.length)return;
  const g=svg.querySelector(".xh");if(!g)return;
  const t0=+svg.dataset.t0,t1=+svg.dataset.t1,L=+svg.dataset.l,R=+svg.dataset.r,W=+svg.dataset.w,T=+svg.dataset.t,B=+svg.dataset.b,H=+svg.dataset.h;
  const line=g.querySelector("line"),dot=g.querySelector("circle"),box=g.querySelector("rect"),[t1El,t2El]=g.querySelectorAll("text");
  const path=svg.querySelector("path.line");
  const X=t=>L+(t-t0)/((t1-t0)||1)*(W-L-R);
  const times=rows.map(r=>Date.parse(r[0]));
  function yOnLine(x){
    /* walk the drawn path for the y at this x: cheap at a few hundred points */
    if(!path)return T;const n=path.getTotalLength();let a=0,b=n;
    for(let k=0;k<18;k++){const m=(a+b)/2;if(path.getPointAtLength(m).x<x)a=m;else b=m;}
    return path.getPointAtLength((a+b)/2).y;
  }
  function show(clientX){
    const r=svg.getBoundingClientRect();const x=(clientX-r.left)/r.width*W;
    if(x<L||x>W-R){g.style.display="none";return;}
    const t=t0+(x-L)/(W-L-R)*(t1-t0);
    let i=0;while(i<times.length-1&&Math.abs(times[i+1]-t)<Math.abs(times[i]-t))i++;
    const row=rows[i];const xx=X(times[i]);const yy=yOnLine(xx);
    line.setAttribute("x1",xx);line.setAttribute("x2",xx);dot.setAttribute("cx",xx);dot.setAttribute("cy",yy);
    t1El.textContent=row[1];t2El.textContent=row[2]||"";
    const w1=row[1].length*6.4,w2=(row[2]||"").length*6.4,bw=Math.max(w1,w2)+16,bh=row[2]?34:20;
    let bx=xx+10;if(bx+bw>W-R)bx=xx-10-bw;const by=Math.max(T,Math.min(yy-bh/2,H-B-bh));
    box.setAttribute("x",bx);box.setAttribute("y",by);box.setAttribute("width",bw);box.setAttribute("height",bh);
    t1El.setAttribute("x",bx+8);t1El.setAttribute("y",by+13.5);t2El.setAttribute("x",bx+8);t2El.setAttribute("y",by+28);
    g.style.display="";
  }
  svg.addEventListener("mousemove",e=>show(e.clientX));
  svg.addEventListener("mouseleave",()=>{g.style.display="none";});
  svg.addEventListener("touchstart",e=>{show(e.touches[0].clientX);},{passive:true});
  svg.addEventListener("touchmove",e=>{show(e.touches[0].clientX);},{passive:true});
}
/* ONE MOTION, ON LOAD: the line draws in and the shading under it is
   revealed to exactly the same x, frame by frame, then the dots appear.
   Once per render; a reader who asked for reduced motion gets the
   finished chart at once. */
function drawIn(svg){
  const path=svg.querySelector("path.line"),reveal=svg.querySelector("clipPath rect.reveal");
  if(!path)return;
  if(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches){svg.classList.add("drawn");return;}
  const n=path.getTotalLength();const T=900,t0=performance.now();
  svg.classList.add("animating");
  path.style.strokeDasharray=n;path.style.strokeDashoffset=n;
  if(reveal)reveal.setAttribute("width",0);
  function frame(now){
    const p=Math.min(1,(now-t0)/T),e=1-Math.pow(1-p,3);   /* ease-out */
    path.style.strokeDashoffset=n*(1-e);
    if(reveal)reveal.setAttribute("width",Math.max(0,path.getPointAtLength(n*e).x));
    if(p<1)requestAnimationFrame(frame);
    else{path.style.strokeDasharray="";path.style.strokeDashoffset="";if(reveal)reveal.setAttribute("width",svg.viewBox.baseVal.width);svg.classList.remove("animating");svg.classList.add("drawn");}
  }
  requestAnimationFrame(frame);
}
function recordBlock(r){
  const raw=HIST[r.tk];
  const px=PRICES_DAILY;
  const havePx=!!(px&&px.length>1),haveRec=!!(raw&&raw.length);
  let mode=window._chartMode||"price";
  if(mode==="price"&&!havePx)mode="pct";
  if(mode!=="price"&&!haveRec&&havePx)mode="price";
  /* the chips carry the only words: what each line is, on hover */
  const modes=[["price","Price","the share price: daily closes, split-adjusted. Dots sit at the price on the filing"],
               ["pct","Stake","the share of the company, one point per month-end: it moves when the holding changes and when the share count changes. Steps without a dot are grants, gifts, or the share count changing"]];
  const chips=`<div class="chips" role="group" aria-label="chart view">${modes.filter(m=>m[0]==="price"?havePx:haveRec).map(m=>`<button class="chip${mode===m[0]?" on":""}" onclick="setChartMode('${m[0]}')" title="${m[2]}">${m[1]}</button>`).join("")}</div>`;
  /* the dots follow the table's filter: Bought draws purchases, Sold sales,
     All both; the other kinds have no dots to draw */
  const moving=EVENTS.filter(e=>e.tk===r.tk&&unchangedKind(e)===null&&(e.c==="P"||e.c==="S")
    &&(VIEW==="all"||(VIEW==="buys"&&e.c==="P")||(VIEW==="sells"&&e.c==="S")));
  const key=moving.length?`<div class="ckey"><span class="b"><i></i>bought</span><span class="s"><i></i>sold</span></div>`:"";
  if(mode==="price"&&havePx){
    return `<div class="csec crec"><div class="cshead">${chips}</div>
      <div class="cchart">${priceChart(px,moving)}</div>${key}
    </div>`;
  }
  if(!haveRec)return "";
  const pts=cleanHist(r.tk);
  const series=pts.length>1?pts:raw;
  return `<div class="csec crec"><div class="cshead">${chips}</div>
    <div class="cchart">${stakeChart(series,moving)}</div>${key}
  </div>`;
}

/* ---- the trades ---- */
function tradesBlock(r){
  const all=EVENTS.filter(e=>e.tk===r.tk).sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||b.fd.localeCompare(a.fd));
  if(!all.length)return `<div class="csec"><h2>Trades</h2><div class="sub">No purchase or sale on record.</div></div>`;
  const trade=e=>e.c==="P"||e.c==="S";
  /* FIVE KINDS, NAMED FOR WHAT THE ROW IS. "Kept apart" named a rule of
     the home page's summaries; here a reader wants to know what happened.
     Bought and Sold are the market. Compensation is everything the company
     gave and what was sold of it: awards, exercises held or cashed, vests,
     withholding, forfeitures. Transfers are gifts, conversions and the
     rest. Share count is the company's own cover pages. */
  const kindOf=e=>{
    if(e.cover)return "covers";
    const uk=unchangedKind(e);
    if(e.c==="P"&&uk===null)return "buys";
    if(e.c==="S"&&uk===null)return "sells";
    if(e.c==="M"||e.c==="A"||e.c==="F"||e.c==="D")return "comp";
    if(e.c==="S"&&(uk==="exercise"||uk==="vest"||uk==="convert"||uk===""))return "comp";
    return "transfers";
  };
  const moved=e=>e.cover?false:(pctOf(e)?Math.abs(pctOf(e).v)>=1:false);
  /* THE SHARE COUNT IS A ROW TOO. Tesla's July 2026 10-Q raised the
     denominator from 3.76B to 3.95B and Musk's 29.91% became 28.44% with
     no filing of his; the table showed nothing between its top row and
     the card. Each cover page that moved the count is a row from the
     record: no trade, no value, the new denominator and the new percent. */
  const covers=((HIST[r.tk]||[]).filter(h=>/^(10-K|10-Q|20-F|40-F)/.test(h[8]||"")&&h[9])
    .map(h=>({cover:true,tk:r.tk,fd:h[0],td:h[0],tf:h[0],c:"",lb:"shares outstanding restated",form:h[8],os:h[9],ha:h[10],po:h[1],acc:h[11],
              u:h[11]&&r.cik?`https://www.sec.gov/Archives/edgar/data/${r.cik}/${h[11].replace(/-/g,"")}/`:""})));
  const every=[...all,...covers].sort((a,b)=>(b.td||b.fd).localeCompare(a.td||a.fd)||(b.cover?1:0)-(a.cover?1:0));
  const count=k=>every.filter(e=>(k==="all"||kindOf(e)===k)&&(!BIG||moved(e))).length;
  const evs=every.filter(e=>(VIEW==="all"||kindOf(e)===VIEW)&&(!BIG||moved(e)));
  const chip=(v,lab,n)=>`<button class="chip${VIEW===v?" on":""}" onclick="VIEW='${v}';renderOpen(PANEL[0])">${lab} <small>${n}</small></button>`;
  /* WHAT THE TRADE WAS, IN WORDS. One column for one fact: the kind of
     trade and whether it was pre-scheduled come from the same label the
     pipeline wrote, so "Planned sale" is one cell, not a red pill and an
     adjective. Coloured by what it did to the stake. */
  const kind=e=>{
    const uk=unchangedKind(e);
    if(uk==="pre")return {t:e.c==="P"?"Pre-IPO purchase":"Pre-IPO sale",k:"neu",n:evBadge(e).n};
    const words={"scheduled sale":"Planned sale","discretionary sale":"Discretionary sale","sale":"Sale",
      "exercise and sell":"Exercise and sell","exercise, part sold":"Exercise, part sold","vested and sold":"Vest, part sold","convert and sell":"Convert and sell",
      "sale, position unchanged":"Sale, position unchanged","open-market purchase":"Open-market purchase",
      "scheduled purchase":"Planned purchase","purchase, position unchanged":"Purchase, position unchanged",
      "options exercised":"Options exercised, held","options exercised, tax withheld":"Options exercised, tax withheld",
      "award granted":"Award granted","award granted, tax withheld":"Award granted, tax withheld","forfeited":"Forfeited",
      "converted":"Converted","gift":"Gift","shares withheld for tax":"Shares withheld for tax","other transaction":"Other transaction"};
    const t=words[e.lb]||(e.c==="P"?"Purchase":e.c==="S"?"Sale":"Other transaction");
    const comp=e.c!=="P"&&e.c!=="S";
    const n=comp?"a filing with no purchase or sale that moved the stake: compensation, a gift or a conversion; no market value is stated for it"
      :e.lb==="sale"?"Form 4 had no Rule 10b5-1 box before April 2023; whether this sale was pre-scheduled is not on the form":evBadge(e).n;
    return {t,k:comp?"neu":uk!==null?"neu":e.c==="P"?"up":"down",n};
  };
  const cell=e=>{
    const p=pctOf(e);const uk=unchangedKind(e);const kd=kind(e);
    const stkTxt=uk==="pre"?"pre-IPO":uk!==null?(p?stakeChange(p.v,p.approx):"unchanged"):p?stakeChange(p.v,p.approx):"not stated";
    const stkCls=p?(p.v>=0?"plus":"minus"):"";
    const span=e.tf&&e.tf!==e.td?`${e.tf} to ${e.td.slice(5)}`:(e.td||e.fd);
    return {kd,p,uk,stkTxt,stkCls,span};
  };
  const rows=evs.map(e=>{
    if(e.cover)return `<tr class="cov"><td class="d" title="the company's cover page, dated ${e.fd}">${e.fd}</td>
      <td class="ty neu" title="the company restated its shares outstanding on this cover page; nothing of the chief executive's moved"><i></i>Shares outstanding restated (${esc(e.form)})</td>
      <td class="n v lv">&mdash;</td><td class="n sh lv">&mdash;</td><td class="n stk">&mdash;</td>
      <td class="n lv">${e.ha?fmt(e.ha):"&mdash;"}</td>
      <td class="n lv">${fmt(e.os)}</td>
      <td class="n lv po">${e.po!==null&&e.po!==undefined?e.po.toFixed(e.po<1?3:2)+"%":"&mdash;"}</td>
      <td class="f">${e.u?`<a href="${e.u}" target="_blank" rel="noopener" title="the filing, on EDGAR">${esc(e.form)} ↗</a>`:""}</td></tr>`;
    const {kd,p,uk,stkTxt,stkCls,span}=cell(e);
    return `<tr><td class="d" title="traded ${spanDay(e,d=>d)}; filed ${e.fd}${lagNote(e)}">${span}</td>
      <td class="ty ${kd.k}" title="${esc(kd.n)}"><i></i>${kd.t}</td>
      <td class="n v ${e.c==="P"?"up":e.c==="S"?"down":"lv"}">${e.c==="P"||e.c==="S"?evValCell(e):"&mdash;"}</td>
      <td class="n sh ${e.c==="P"?"up":e.c==="S"?"down":(e.nc>=0?"up":"down")}">${e.c==="P"||(e.c!=="S"&&e.nc>=0)?"+":"−"}${fmt(e.sh)}</td>
      <td class="n stk ${stkCls}" title="${uk===null&&!p?esc(pctWhy(e)):"what this filing did to the stake, against the stake as the day opened"}">${stkTxt.replace(/^stake /,"")}</td>
      <td class="n lv" title="shares held at the end of this filing's day, per the record; filings on one day share it">${e.ha?fmt(e.ha):"&mdash;"}</td>
      <td class="n lv" title="shares outstanding on record that day: the company's last cover page before it">${e.os?fmt(e.os):"&mdash;"}</td>
      <td class="n lv po" title="the stake at the end of the day: held over outstanding">${e.po!==null&&e.po!==undefined?e.po.toFixed(e.po<1?3:2)+"%":"&mdash;"}</td>
      <td class="f">${e.u?`<a href="${filingPage(e.u)}" target="_blank" rel="noopener" title="the filing, on EDGAR">Form 4 ↗</a>`:""}</td></tr>`}).join("");
  /* the export is the same rows as text, in the same order */
  window.exportTrades=()=>{
    const head=["date_from","date_to","filed","type","value_usd","shares","stake_change_pct","held_after","shares_outstanding","owned_pct","filing"];
    const lines=[head.join(",")].concat(evs.map(e=>{
      if(e.cover)return [e.fd,e.fd,e.fd,`Shares outstanding restated (${e.form})`,"","","",e.ha||"",e.os||"",(e.po!==null&&e.po!==undefined)?e.po.toFixed(4):"",e.u||""].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(",");
      const {kd,p,uk}=cell(e);
      return [e.tf||e.td||e.fd,e.td||e.fd,e.fd,kd.t,e.fl?"":(e.v||""),(e.c==="P"?"":"-")+(e.sh||""),
              p?p.v.toFixed(4):(uk!==null?"0":""),e.ha||"",e.os||"",(e.po!==null&&e.po!==undefined)?e.po.toFixed(4):"",e.u||""].map(v=>`"${String(v).replace(/"/g,'""')}"`).join(",");
    }));
    const blob=new Blob([lines.join("\n")],{type:"text/csv"});
    const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`${r.tk}-trades.csv`;a.click();
  };
  const bigChip=`<button class="chip big${BIG?" on":""}" onclick="BIG=!BIG;renderOpen(PANEL[0])" title="only the rows that moved the stake by at least 1% of what it was">Moved the stake &ge; 1%</button>`;
  return `<div class="csec ctrades"><div class="thead"><h2>Trades</h2><button class="export" onclick="exportTrades()">Export CSV</button></div>
    <div class="tchips">${chip("all","All",count("all"))}${chip("buys","Bought",count("buys"))}${chip("sells","Sold",count("sells"))}${chip("comp","Compensation",count("comp"))}${chip("transfers","Transfers",count("transfers"))}${chip("covers","Share count",count("covers"))}<span class="tsep"></span>${bigChip}</div>
    ${rows?`<table><thead><tr><th>Date</th><th>Trade</th><th class="n">Value</th><th class="n">Shares</th><th class="n">Change</th><th class="n lv">Held</th><th class="n lv">Outstanding</th><th class="n lv">Owned</th><th class="f">Filing</th></tr></thead><tbody>${rows}</tbody></table>`:`<div class="sub">Nothing in this view.</div>`}
    ${VIEW==="comp"?`<div class="sub" style="margin-top:10px">Compensation: what the company gave and what was sold of it. Awards granted, options exercised and held or cashed, vests, tax withholding, forfeitures. None of it is counted as buying or selling in the site's summaries.</div>`:""}
    ${VIEW==="transfers"?`<div class="sub" style="margin-top:10px">Transfers: gifts, conversions between classes, pre-IPO catch-ups and other non-market transactions the filing reports.</div>`:""}
    ${VIEW==="covers"?`<div class="sub" style="margin-top:10px">Share count: the company's cover pages that changed the number of shares outstanding. The stake moves with them though nothing of the chief executive's did.</div>`:""}
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
    <b style="color:var(--ink)">${verdict}</b>. The proxy statement says: <q>${esc(ev)}</q>
    <span class="src">${link?`<a href="${link}" target="_blank" rel="noopener">${esc(src)} ↗</a>`:esc(src||"the proxy statement")}</span></div>`;
}

function reportBlock(r){
  const subj=encodeURIComponent(`${r.tk}: a figure looks wrong`);
  const body=encodeURIComponent(`Company: ${r.co} (${r.tk})\nWhat I see: \nWhat I think it should be: \nWhere I checked: \n\nPage: https://founderledequities.com/company/${r.tk}/`);
  return `Computed from SEC EDGAR, never estimated. Prices are the ${PRICES_ASOF||"latest"} close.
    If a number looks wrong, <a href="mailto:hello@founderledequities.com?subject=${subj}&body=${body}">say so</a>; every figure links to the filing it came from.`;
}

function renderOpen(r,{animate=true}={}){
  window._lastRow=r;
  $("#cbody").innerHTML=band(r)+recordBlock(r)+tradesBlock(r)+whyBlock(r);
  $("#creport").innerHTML=reportBlock(r);
  const svg=document.querySelector(".cchart svg.fchart");
  if(svg){attachHover(svg);if(animate)drawIn(svg);}
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
  renderOpen(row,{animate:false});   /* the numbers first; the record and trades fill in */
  const base=(C.sp||!pro)?"":"/pro";
  const [h,e,p]=await Promise.all([
    fetchText([`${base}/history/${C.tk}.csv`,`/history/${C.tk}.csv`]),
    fetchText([`${base}/events/${C.tk}.csv`,`/events/${C.tk}.csv`]),
    fetchText([`/prices/${C.tk}.csv`])]);   /* prices are public on every page */
  if(h){const m=mapHistory(parseCSV(h));if(m[C.tk])HIST=m;}
  if(e){EVENTS=mapEvents(parseCSV(e)).filter(x=>x.tk===C.tk);}
  if(p){PRICES_DAILY=parseCSV(p).map(r=>[String(r.date||"").slice(0,10),num(r.close)]).filter(x=>x[0].length===10&&x[1]>0);if(!PRICES_DAILY.length)PRICES_DAILY=null;}
  renderOpen(row);
})();

function setChartMode(m){window._chartMode=m;if(window._lastRow)renderOpen(window._lastRow);}
let _rsz=null;window.addEventListener("resize",()=>{clearTimeout(_rsz);_rsz=setTimeout(()=>{if(window._lastRow)renderOpen(window._lastRow,{animate:false});},150);});
